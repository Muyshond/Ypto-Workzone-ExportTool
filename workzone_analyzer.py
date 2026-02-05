#!/usr/bin/env python3

import zipfile
import json
import os
import sys
from collections import defaultdict

class WorkzoneAnalyzer:
    def __init__(self):
        self.data = {
            'spaces': [],
            'workpages': [],
            'relations_sp_wp': [],
            'relations_wp_vz': [],
            'business_apps': [],
            'roles': [],
            'metadata': {},
            'direct_role_relations': {} 
        }

    def load_json(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return None

    def find_and_load_files(self, base_path):
        """Zoekt generiek naar de juiste bestanden in de export structuur"""
        for root, _, files in os.walk(base_path):
            for file in files:
                full_path = os.path.join(root, file)
                
                if file in ['export_data', 'export_metadata.json']:
                    self.data['metadata'] = self.load_json(full_path)
                elif file == '1_DataFile_SP.json':
                    self.data['spaces'] = self.load_json(full_path)
                elif file == '1_DataFile_WPV.json':
                    self.data['workpages'] = self.load_json(full_path)
                elif file == '1_DataFile_SP-WP.json':
                    self.data['relations_sp_wp'] = self.load_json(full_path)
                elif file == '1_DataFile_WP-VZ.json':
                    self.data['relations_wp_vz'] = self.load_json(full_path)
                
                elif 'businessapp' in root.lower() and file.endswith('.json'):
                    content = self.load_json(full_path)
                    if isinstance(content, list): self.data['business_apps'].extend(content)
                elif 'role' in root.lower() and file.endswith('.json'):
                    if 'relations' in root.lower():
                        content = self.load_json(full_path)
                        if content and 'id' in content:
                            role_id = content['id']
                            self.data['direct_role_relations'][role_id] = content.get('relations', {})
                    else:
                        content = self.load_json(full_path)
                        if isinstance(content, list): self.data['roles'].extend(content)

    def extract_zip_recursive(self, zip_path, extract_to):
        print(f"Unzipping {os.path.basename(zip_path)}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)

        for root, _, files in os.walk(extract_to):
            for file in files:
                if file.endswith('.zip'):
                    nested_path = os.path.join(root, file)
                    nested_extract = os.path.join(root, file.replace('.zip', '_content'))
                    self.extract_zip_recursive(nested_path, nested_extract)

    def generate_report(self):
        report = {
            "statistics": {},
            "structure": [],
            "roles_analysis": []
        }

        wp_viz_map = defaultdict(list)
        for rel in self.data['relations_wp_vz']:
            wp_viz_map[rel.get('workPageId')].append(rel.get('visualizationId'))

        sp_wp_map = defaultdict(list)
        for rel in self.data['relations_sp_wp']:
            sp_wp_map[rel.get('spaceId')].append(rel.get('workPageId'))

        for sp in self.data['spaces']:
            if sp.get('language') not in ['master', 'en']: continue
            space_node = {
                "space_title": sp.get('mergedEntity', {}).get('value', {}).get('title', 'Unknown'),
                "space_id": sp.get('id'),
                "pages": []
            }
            for wp_id in sp_wp_map.get(sp.get('id'), []):
                wp_details = next((w for w in self.data['workpages'] if w.get('id') == wp_id), {})
                viz_ids = wp_viz_map.get(wp_id, [])
                space_node["pages"].append({
                    "page_title": wp_details.get('mergedEntity', {}).get('descriptor', {}).get('value', {}).get('title', wp_id),
                    "page_id": wp_id,
                    "apps": [vid.split('#')[0] for vid in viz_ids]
                })
            report["structure"].append(space_node)

        for role in self.data['roles']:
            role_id = role.get('cdm', {}).get('identification', {}).get('id')
            provider = role.get('cdm', {}).get('identification', {}).get('providerId')
            
            apps_in_role = []
            spaces_in_role = []
            
            for app in self.data['business_apps']:
                app_id = app.get('cdm', {}).get('identification', {}).get('id')
                app_relations = app.get('cdm', {}).get('relations', {}).get('roles', [])
                if any(r.get('target', {}).get('id') == role_id for r in app_relations):
                    apps_in_role.append(app_id)

            if role_id in self.data['direct_role_relations']:
                direct_rels = self.data['direct_role_relations'][role_id]
                spaces_in_role = direct_rels.get('space', [])
                
                for a_id in direct_rels.get('businessapp', []):
                    if a_id not in apps_in_role:
                        apps_in_role.append(a_id)

            report["roles_analysis"].append({
                "role_id": role_id,
                "provider_id": provider,
                "app_count": len(apps_in_role),
                "apps": apps_in_role, 
                "spaces": spaces_in_role
            })

        report["statistics"] = {
            "total_spaces": len([s for s in self.data['spaces'] if s.get('language') == 'master']),
            "total_roles": len(self.data['roles']),
            "total_apps": len(self.data['business_apps'])
        }
        return report

def main():
    if len(sys.argv) < 2:
        return

    zip_file = sys.argv[1]
    extract_dir = "temp_workzone_data"
    
    analyzer = WorkzoneAnalyzer()
    analyzer.extract_zip_recursive(zip_file, extract_dir)
    analyzer.find_and_load_files(extract_dir)
    
    report = analyzer.generate_report()

    with open('workzone_full_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    main()