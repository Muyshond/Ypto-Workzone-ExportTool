import * as fs from 'fs';
import * as path from 'path';
import AdmZip from 'adm-zip';

interface WorkzoneData {
    spaces: any[];
    workpages: any[];
    relations_sp_wp: any[];
    relations_wp_vz: any[];
    business_apps: any[];
    roles: any[];
    metadata: any;
    direct_role_relations: Record<string, any>;
}

interface RoleAnalysis {
    role_id: string;
    provider_id: string | null;
    app_count: number;
    apps: string[];
    space_count: number;
    spaces: string[];
}

interface Report {
    statistics: {
        total_spaces: number;
        total_roles: number;
        total_apps: number;
    };
    structure: any[];
    roles_analysis: RoleAnalysis[];
}

interface UI5Node {
    id: string;
    type: string;
    title: string;
    fullId?: string;
    providerId?: string;
    pageCount?: number;
    appCount?: number;
    spaceCount?: number;
    totalPages?: number;
    totalApps?: number;
    children?: UI5Node[];
}

interface UI5Report {
    roles: UI5Node[];
    statistics: {
        totalRoles: number;
        totalSpaces: number;
        totalPages: number;
        totalApps: number;
    };
}

class WorkzoneAnalyzer {
    private data: WorkzoneData = {
        spaces: [],
        workpages: [],
        relations_sp_wp: [],
        relations_wp_vz: [],
        business_apps: [],
        roles: [],
        metadata: {},
        direct_role_relations: {}
    };

    private loadJson(filePath: string): any | null {
        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            return JSON.parse(content);
        } catch (e) {
            console.error(`Error loading ${filePath}:`, e);
            return null;
        }
    }

    public findAndLoadFiles(basePath: string): void {
        const walk = (dir: string) => {
            const files = fs.readdirSync(dir);
            
            files.forEach(file => {
                const fullPath = path.join(dir, file);
                const stat = fs.statSync(fullPath);
                
                if (stat.isDirectory()) {
                    walk(fullPath);
                } else {
                    if (file === 'export_data' || file === 'export_metadata.json') {
                        this.data.metadata = this.loadJson(fullPath);
                    } else if (file === '1_DataFile_SP.json') {
                        this.data.spaces = this.loadJson(fullPath);
                    } else if (file === '1_DataFile_WPV.json') {
                        this.data.workpages = this.loadJson(fullPath);
                    } else if (file === '1_DataFile_SP-WP.json') {
                        this.data.relations_sp_wp = this.loadJson(fullPath);
                    } else if (file === '1_DataFile_WP-VZ.json') {
                        this.data.relations_wp_vz = this.loadJson(fullPath);
                    } else if (dir.toLowerCase().includes('businessapp') && file.endsWith('.json')) {
                        const content = this.loadJson(fullPath);
                        if (Array.isArray(content)) {
                            this.data.business_apps.push(...content);
                        }
                    } else if (dir.toLowerCase().includes('role') && file.endsWith('.json')) {
                        if (dir.toLowerCase().includes('relations')) {
                            const content = this.loadJson(fullPath);
                            if (content && content.id) {
                                this.data.direct_role_relations[content.id] = content.relations || {};
                            }
                        } else {
                            const content = this.loadJson(fullPath);
                            if (Array.isArray(content)) {
                                this.data.roles.push(...content);
                            }
                        }
                    }
                }
            });
        };
        
        walk(basePath);
    }

    public extractZipRecursive(zipPath: string, extractTo: string): void {
        console.log(`Unzipping ${path.basename(zipPath)}`);
        
        const zip = new AdmZip(zipPath);
        zip.extractAllTo(extractTo, true);

        const walk = (dir: string) => {
            const files = fs.readdirSync(dir);
            
            files.forEach(file => {
                const fullPath = path.join(dir, file);
                const stat = fs.statSync(fullPath);
                
                if (stat.isDirectory()) {
                    walk(fullPath);
                } else if (file.endsWith('.zip')) {
                    const nestedExtract = path.join(dir, file.replace('.zip', '_content'));
                    this.extractZipRecursive(fullPath, nestedExtract);
                }
            });
        };
        
        walk(extractTo);
    }

    public generateReport(): Report {
        const report: Report = {
            statistics: {
                total_spaces: 0,
                total_roles: 0,
                total_apps: 0
            },
            structure: [],
            roles_analysis: []
        };

        const wpVizMap: Record<string, string[]> = {};
        this.data.relations_wp_vz.forEach(rel => {
            const wpId = rel.workPageId;
            if (!wpVizMap[wpId]) wpVizMap[wpId] = [];
            wpVizMap[wpId].push(rel.visualizationId);
        });

        const spWpMap: Record<string, string[]> = {};
        this.data.relations_sp_wp.forEach(rel => {
            const spId = rel.spaceId;
            if (!spWpMap[spId]) spWpMap[spId] = [];
            spWpMap[spId].push(rel.workPageId);
        });

        this.data.spaces.forEach(sp => {
            if (!['master', 'en'].includes(sp.language)) return;
            
            const spaceNode: any = {
                space_title: sp.mergedEntity?.value?.title || 'Unknown',
                space_id: sp.id,
                pages: []
            };

            const wpIds = spWpMap[sp.id] || [];
            wpIds.forEach(wpId => {
                const wpDetails = this.data.workpages.find(w => w.id === wpId);
                const vizIds = wpVizMap[wpId] || [];
                
                spaceNode.pages.push({
                    page_title: wpDetails?.mergedEntity?.descriptor?.value?.title || wpId,
                    page_id: wpId,
                    apps: vizIds.map(vid => vid.split('#')[0])
                });
            });
            
            report.structure.push(spaceNode);
        });

        this.data.roles.forEach(role => {
            const roleId = role.cdm?.identification?.id;
            const provider = role.cdm?.identification?.providerId;
            
            const appsInRole: string[] = [];
            const spacesInRole: string[] = [];
            
            this.data.business_apps.forEach(app => {
                const appId = app.cdm?.identification?.id;
                const appRelations = app.cdm?.relations?.roles || [];
                
                if (appRelations.some((r: any) => r.target?.id === roleId)) {
                    appsInRole.push(appId);
                }
            });

            if (this.data.direct_role_relations[roleId]) {
                const directRels = this.data.direct_role_relations[roleId];
                const spaces = directRels.space || [];
                spacesInRole.push(...spaces);
                
                const businessapps = directRels.businessapp || [];
                businessapps.forEach((aId: string) => {
                    if (!appsInRole.includes(aId)) {
                        appsInRole.push(aId);
                    }
                });
            }

            report.roles_analysis.push({
                role_id: roleId,
                provider_id: provider,
                app_count: appsInRole.length,
                apps: appsInRole,
                space_count: spacesInRole.length,
                spaces: spacesInRole
            });
        });

        report.statistics = {
            total_spaces: this.data.spaces.filter(s => s.language === 'master').length,
            total_roles: this.data.roles.length,
            total_apps: this.data.business_apps.length
        };

        return report;
    }

    public generateUI5Hierarchy(): UI5Report {
        const wpVizMap: Record<string, string[]> = {};
        this.data.workpages.forEach(wp => {
            if (wp.language === 'en') {
                wpVizMap[wp.id] = wp.workPageVizsId || [];
            }
        });

        const spWpMap: Record<string, string[]> = {};
        const wpSpMap: Record<string, string> = {};
        this.data.relations_sp_wp.forEach(rel => {
            const spId = rel.spaceId;
            const wpId = rel.workPageId;
            if (!spWpMap[spId]) spWpMap[spId] = [];
            spWpMap[spId].push(wpId);
            wpSpMap[wpId] = spId;
        });

        const spaceDetails: Record<string, UI5Node> = {};
        this.data.spaces.forEach(sp => {
            if (!['master', 'en'].includes(sp.language)) return;
            
            const spId = sp.id;
            const spaceNode: UI5Node = {
                id: spId,
                type: 'space',
                title: sp.mergedEntity?.value?.title || sp.descriptor?.value?.title || 'Unknown Space',
                pageCount: 0,
                appCount: 0,
                children: []
            };

            const wpIds = spWpMap[spId] || [];
            wpIds.forEach(wpId => {
                const wpDetails = this.data.workpages.find(w => w.id === wpId && w.language === 'en');
                if (!wpDetails) return;
                
                const vizIds = wpVizMap[wpId] || [];
                const cleanedVizIds = vizIds.map(vid => vid.split('#')[0]);

                const pageNode: UI5Node = {
                    id: wpId,
                    type: 'page',
                    title: wpDetails.mergedEntity?.descriptor?.value?.title || wpId,
                    appCount: cleanedVizIds.length,
                    children: []
                };

                cleanedVizIds.forEach(appId => {
                    pageNode.children!.push({
                        id: appId,
                        type: 'app',
                        title: appId.includes('_') ? appId.split('_').pop()! : appId,
                        fullId: appId
                    });
                });

                spaceNode.children!.push(pageNode);
                spaceNode.pageCount!++;
                spaceNode.appCount! += cleanedVizIds.length;
            });
            
            spaceDetails[spId] = spaceNode;
        });

        const rolesHierarchy: UI5Node[] = [];
        
        this.data.roles.forEach(role => {
            const roleId = role.cdm?.identification?.id;
            const providerId = role.cdm?.identification?.providerId;
            
            const roleApps: string[] = [];
            const roleSpaces: Record<string, UI5Node> = {};
            let totalApps = 0;

            this.data.business_apps.forEach(app => {
                const appId = app.cdm?.identification?.id;
                const appRelations = app.cdm?.relations?.roles || [];
                
                if (appRelations.some((r: any) => r.target?.id === roleId)) {
                    roleApps.push(appId);
                }
            });

            if (this.data.direct_role_relations[roleId]) {
                const directRels = this.data.direct_role_relations[roleId];
                const spaceIds = directRels.space || [];
                
                const businessapps = directRels.businessapp || [];
                businessapps.forEach((aId: string) => {
                    if (!roleApps.includes(aId)) {
                        roleApps.push(aId);
                    }
                });
                
                spaceIds.forEach((spaceId: string) => {
                    if (spaceDetails[spaceId]) {
                        roleSpaces[spaceId] = JSON.parse(JSON.stringify(spaceDetails[spaceId]));
                        totalApps += roleSpaces[spaceId].appCount || 0;
                    }
                });
            }

            if (providerId) {
                this.data.workpages.forEach(wp => {
                    if (wp.language !== 'en') return;
                    
                    const wpId = wp.id;
                    const wpTitle = wp.mergedEntity?.descriptor?.value?.title;
                    const vizIds = wp.workPageVizsId || [];
                    
                    const matchedApps: string[] = [];
                    vizIds.forEach((vizId: string) => {
                        if (vizId.startsWith(providerId + '_') || vizId.includes(providerId)) {
                            matchedApps.push(vizId.split('#')[0]);
                        }
                    });
                    
                    if (matchedApps.length > 0) {
                        const spaceId = wpSpMap[wpId];
                        if (spaceId && spaceDetails[spaceId]) {
                            if (!roleSpaces[spaceId]) {
                                roleSpaces[spaceId] = {
                                    id: spaceId,
                                    type: 'space',
                                    title: spaceDetails[spaceId].title,
                                    pageCount: 0,
                                    appCount: 0,
                                    children: []
                                };
                            }
                            
                            const pageNode: UI5Node = {
                                id: wpId,
                                type: 'page',
                                title: wpTitle,
                                appCount: matchedApps.length,
                                children: []
                            };
                            
                            matchedApps.forEach(appId => {
                                pageNode.children!.push({
                                    id: appId,
                                    type: 'app',
                                    title: appId.includes('_') ? appId.split('_').pop()! : appId,
                                    fullId: appId
                                });
                                totalApps++;
                            });
                            
                            roleSpaces[spaceId].children!.push(pageNode);
                            roleSpaces[spaceId].pageCount!++;
                            roleSpaces[spaceId].appCount! += matchedApps.length;
                        }
                    }
                });
            }

            const roleNode: UI5Node = {
                id: roleId,
                type: 'role',
                title: roleId.includes('_') ? roleId.split('_').pop()! : roleId,
                fullId: roleId,
                providerId: providerId || 'BTP',
                spaceCount: Object.keys(roleSpaces).length,
                totalPages: Object.values(roleSpaces).reduce((sum, s) => sum + (s.pageCount || 0), 0),
                totalApps: totalApps + roleApps.length,
                children: []
            };
            
            Object.values(roleSpaces).forEach(space => {
                roleNode.children!.push(space);
            });
            
            roleApps.forEach(appId => {
                roleNode.children!.push({
                    id: appId,
                    type: 'app',
                    title: appId.includes('_') ? appId.split('_').pop()! : appId,
                    fullId: appId
                });
            });
            
            rolesHierarchy.push(roleNode);
        });

        return {
            roles: rolesHierarchy,
            statistics: {
                totalRoles: this.data.roles.length,
                totalSpaces: this.data.spaces.filter(s => ['master', 'en'].includes(s.language)).length,
                totalPages: this.data.workpages.filter(w => w.language === 'en').length,
                totalApps: this.data.business_apps.length
            }
        };
    }
}

function main(): void {
    const args = process.argv.slice(2);
    
    if (args.length < 1) {
        console.log('Usage: ts-node workzone_analyzer.ts <zip_file>');
        return;
    }

    const zipFile = args[0];
    const extractDir = 'temp_workzone_data';
    
    const analyzer = new WorkzoneAnalyzer();
    analyzer.extractZipRecursive(zipFile, extractDir);
    analyzer.findAndLoadFiles(extractDir);
    
    const report = analyzer.generateReport();
    const ui5Report = analyzer.generateUI5Hierarchy();

    fs.writeFileSync('workzone_full_report.json', JSON.stringify(report, null, 2));
    fs.writeFileSync('workzone_ui5_hierarchy.json', JSON.stringify(ui5Report, null, 2));
    
    console.log('Generated: workzone_full_report.json');
    console.log('Generated: workzone_ui5_hierarchy.json');
}

main();