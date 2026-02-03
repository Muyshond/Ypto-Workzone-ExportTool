#!/usr/bin/env python3


import zipfile
import json
import os
import sys
from datetime import datetime
from collections import defaultdict


def unzip_recursive(zip_path, extract_to):
    """Unzip een bestand en unzip recursief alle geneste zip bestanden"""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    
    # Zoek naar geneste zip bestanden
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            if file.endswith('.zip'):
                nested_zip_path = os.path.join(root, file)
                nested_extract_to = os.path.join(root, file.replace('.zip', ''))
                print(f"  Unzipping geneste file: {file}")
                unzip_recursive(nested_zip_path, nested_extract_to)


def load_workzone_data(base_path):
    """Laad alle SAP Workzone data"""
    
    data = {}
    
    # Laad export metadata
    export_data_path = os.path.join(base_path, 'export_data')
    if os.path.exists(export_data_path):
        with open(export_data_path, 'r') as f:
            data['export_metadata'] = json.load(f)
    
    # Laad roles
    roles_path = os.path.join(base_path, 'sub_account/SUB_ACCOUNT/role/role1.json')
    if os.path.exists(roles_path):
        with open(roles_path, 'r') as f:
            data['roles'] = json.load(f)
    
    # Laad business apps
    apps_path = os.path.join(base_path, 'sub_account/SUB_ACCOUNT/businessapp/businessapp1.json')
    if os.path.exists(apps_path):
        with open(apps_path, 'r') as f:
            data['business_apps'] = json.load(f)
    
    # Laad content data
    content_path = os.path.join(base_path, 'agents/cep-runtime-agent/content')
    
    if os.path.exists(os.path.join(content_path, '1_DataFile_SP.json')):
        with open(os.path.join(content_path, '1_DataFile_SP.json'), 'r') as f:
            data['spaces'] = json.load(f)
    
    if os.path.exists(os.path.join(content_path, '1_DataFile_WPV.json')):
        with open(os.path.join(content_path, '1_DataFile_WPV.json'), 'r') as f:
            data['workpages'] = json.load(f)
    
    if os.path.exists(os.path.join(content_path, '1_DataFile_SP-WP.json')):
        with open(os.path.join(content_path, '1_DataFile_SP-WP.json'), 'r') as f:
            data['space_workpage_relations'] = json.load(f)
    
    return data


def extract_app_name_from_viz(viz_id):
    """Extract leesbare app naam uit visualization ID"""
    # Verschillende formaten:
    # - saas_approuter_be.nmbs.scanner#Scanner-demo
    # - be.nmbs.scm.zscmcustomcard.app#be.nmbs.scm.zscmcustomcard.viz
    # - 303d0e01-17d3-4850-a8fb-032a635b3344#Default-VizId
    # - gbx_0D6EB5511EA3B7334E8190B6BB78DF5D#008Y17F6AD9DN5414LTUOAPRX
    
    parts = viz_id.split("#")
    app_part = parts[0]
    
    # Als het een GUID is, return de volledige ID
    if app_part.count('-') >= 4:
        return app_part
    
    # Als het gbx_ format is, return dat
    if app_part.startswith('gbx_'):
        return app_part
    
    # Anders, split op _ en neem het laatste deel
    if '_' in app_part:
        # Voor saas_approuter_be.nmbs.scanner -> be.nmbs.scanner
        parts = app_part.split('_', 1)
        if len(parts) > 1:
            return parts[1]
    
    # Voor be.nmbs.scm.zscmcustomcard.app -> zscmcustomcard
    if '.' in app_part:
        parts = app_part.split('.')
        # Vind het deel dat begint met z of is het laatste deel voor .app
        for part in parts:
            if part.startswith('z') and len(part) > 3:
                return part
        # Als er geen z-deel is, return het laatste betekenisvolle deel
        meaningful = [p for p in parts if p not in ['app', 'viz', 'be', 'nmbs', 'scm', 'btc']]
        if meaningful:
            return meaningful[-1]
    
    return app_part


def analyze_workzone_export(data):
    """Analyseer de Workzone data en maak een overzicht"""
    
    overview = {
        "export_info": {},
        "spaces": [],
        "pages": [],
        "apps": [],
        "roles": [],
        "statistics": {}
    }
    
    # Export info
    if 'export_metadata' in data:
        meta = data['export_metadata']
        overview["export_info"] = {
            "date": meta.get("time"),
            "exported_by": meta.get("username"),
            "product": meta.get("productName"),
            "version": meta.get("transportServiceVersion"),
            "provider_ids": meta.get("providerIds", [])
        }
    
    # Spaces
    if 'spaces' in data:
        for space in data['spaces']:
            if space.get('language') == 'master':
                overview["spaces"].append({
                    "id": space.get("id"),
                    "title": space.get("mergedEntity", {}).get("title"),
                    "sort_number": space.get("mergedEntity", {}).get("sortNumber"),
                    "description": space.get("mergedEntity", {}).get("description")
                })
    
    # Map visualization IDs to app names
    viz_to_app_map = {}
    app_details = {}
    
    # Verwerk business apps eerst
    if 'business_apps' in data:
        for app in data['business_apps']:
            app_id = app.get("cdm", {}).get("identification", {}).get("id")
            title = app.get("cdm", {}).get("texts", {}).get("cdm|identification|title", {}).get("value", {}).get("")
            
            if not title:
                base_relation = app.get("cdm", {}).get("relations", {}).get("base", [])
                if base_relation:
                    extended_id = base_relation[0].get("target", {}).get("id")
                    title = extract_app_name_from_viz(extended_id)
                else:
                    title = extract_app_name_from_viz(app_id)
            
            app_details[app_id] = {
                "id": app_id,
                "title": title,
                "provider_id": app.get("cdm", {}).get("identification", {}).get("providerId"),
                "type": "extended" if app.get("cdm", {}).get("relations", {}).get("base") else "custom",
                "created_by": app.get("metadata", {}).get("createdBy"),
                "updated_by": app.get("metadata", {}).get("updatedBy"),
                "pages": [],
                "spaces": []
            }
            
            # Map visualization ID to this app
            viz_to_app_map[app_id] = app_id
    
    # Pages en apps mapping
    page_to_space_map = defaultdict(list)
    
    if 'space_workpage_relations' in data:
        for relation in data['space_workpage_relations']:
            space_id = relation.get("spaceId")
            workpage_id = relation.get("workPageId")
            
            # Vind space title
            space_title = None
            if 'spaces' in data:
                for space in data['spaces']:
                    if space.get("id") == space_id and space.get('language') == 'master':
                        space_title = space.get("mergedEntity", {}).get("title")
                        break
            
            if space_title:
                page_to_space_map[workpage_id].append(space_title)
    
    # Verwerk workpages
    if 'workpages' in data:
        for wp in data['workpages']:
            if wp.get('language') == 'en':
                page_id = wp.get("id")
                page_title = wp.get("mergedEntity", {}).get("descriptor", {}).get("value", {}).get("title")
                viz_ids = wp.get("workPageVizsId", [])
                
                page_info = {
                    "id": page_id,
                    "title": page_title,
                    "description": wp.get("mergedEntity", {}).get("descriptor", {}).get("value", {}).get("description"),
                    "spaces": page_to_space_map.get(page_id, []),
                    "apps": []
                }
                
                # Verwerk alle visualizations in deze page
                for viz_id in viz_ids:
                    app_name = extract_app_name_from_viz(viz_id)
                    
                    # Voeg app toe aan page
                    page_info["apps"].append({
                        "viz_id": viz_id,
                        "app_name": app_name
                    })
                    
                    # Update app details als het een bekende app is
                    for app_id, app in app_details.items():
                        if app_id in viz_id or viz_id.startswith(app_id):
                            if page_title not in app["pages"]:
                                app["pages"].append(page_title)
                            for space in page_info["spaces"]:
                                if space not in app["spaces"]:
                                    app["spaces"].append(space)
                
                overview["pages"].append(page_info)
    
    # Voeg apps toe aan overview
    overview["apps"] = list(app_details.values())
    
    # Roles met afgeleide app en page relaties
    if 'roles' in data:
        for role in data['roles']:
            role_id = role.get("cdm", {}).get("identification", {}).get("id")
            provider_id = role.get("cdm", {}).get("identification", {}).get("providerId")
            
            base_relation = role.get("cdm", {}).get("relations", {}).get("base", [])
            extends = base_relation[0].get("target", {}).get("id") if base_relation else None
            
            # Zoek pages en visualizations die deze role's provider ID gebruiken
            related_pages = []
            related_visualizations = []
            
            if provider_id:
                for page in overview["pages"]:
                    for app in page["apps"]:
                        viz_id = app["viz_id"]
                        # Check of deze visualization de provider gebruikt
                        if viz_id.startswith(provider_id + "_") or provider_id in viz_id:
                            if page["title"] not in related_pages:
                                related_pages.append(page["title"])
                            related_visualizations.append({
                                "page": page["title"],
                                "viz_id": viz_id,
                                "app_name": app["app_name"]
                            })
            
            overview["roles"].append({
                "id": role_id,
                "provider_id": provider_id,
                "extends": extends,
                "created_by": role.get("metadata", {}).get("createdBy"),
                "updated_by": role.get("metadata", {}).get("updatedBy"),
                "related_pages": related_pages,
                "related_visualizations": related_visualizations,
                "note": f"Gevonden via provider matching in {len(related_visualizations)} visualizations" if related_visualizations else "Geen visualizations gevonden met deze provider"
            })
    
    # Statistics
    overview["statistics"] = {
        "total_spaces": len(overview["spaces"]),
        "total_pages": len(overview["pages"]),
        "total_apps": len(overview["apps"]),
        "total_roles": len(overview["roles"]),
        "total_visualizations": sum(len(page["apps"]) for page in overview["pages"])
    }
    
    return overview


def print_overview(overview):
    """Print een leesbaar overzicht"""
    
    print("\n" + "="*80)
    print("SAP WORKZONE EXPORT OVERVIEW")
    print("="*80)
    
    print("\n⚠️  BELANGRIJK:")
    print("   Role-to-user assignments worden NIET geëxporteerd door SAP Workzone.")
    print("   Deze tool toont alleen welke pages/visualizations een role KAN zien")
    print("   op basis van provider ID matching, niet wie welke role heeft.")
    print("   Voor user-to-role toewijzingen, raadpleeg BTP Cockpit of IAS.")
    
    # Export info
    if overview["export_info"]:
        print("\n📦 EXPORT INFORMATIE:")
        print(f"   Datum: {overview['export_info'].get('date')}")
        print(f"   Gebruiker: {overview['export_info'].get('exported_by')}")
        print(f"   Product: {overview['export_info'].get('product')}")
        print(f"   Versie: {overview['export_info'].get('version')}")
    
    # Statistics
    print("\n📊 STATISTIEKEN:")
    stats = overview["statistics"]
    print(f"   Spaces: {stats['total_spaces']}")
    print(f"   Pages: {stats['total_pages']}")
    print(f"   Apps: {stats['total_apps']}")
    print(f"   Roles: {stats['total_roles']}")
    print(f"   Visualisaties: {stats['total_visualizations']}")
    
    # Spaces
    if overview["spaces"]:
        print("\n🏠 SPACES:")
        for space in overview["spaces"]:
            print(f"   - {space['title']}")
    
    # Pages
    if overview["pages"]:
        print("\n📄 PAGES:")
        for page in overview["pages"]:
            print(f"\n   {page['title']}")
            if page["spaces"]:
                print(f"      Spaces: {', '.join(page['spaces'])}")
            print(f"      Aantal apps: {len(page['apps'])}")
            if page["apps"]:
                for app in page["apps"]:
                    print(f"         - {app['app_name']}")
    
    # Apps
    if overview["apps"]:
        print("\n📱 APPS:")
        for app in overview["apps"]:
            print(f"\n   {app['title']}")
            print(f"      ID: {app['id']}")
            print(f"      Type: {app['type']}")
            print(f"      Provider: {app['provider_id']}")
            if app["pages"]:
                print(f"      Pages: {', '.join(app['pages'])}")
            if app["spaces"]:
                print(f"      Spaces: {', '.join(app['spaces'])}")
    
    # Roles
    if overview["roles"]:
        print("\n👥 ROLES EN TOEGANG:")
        for role in overview["roles"]:
            print(f"\n   📌 {role['id']}")
            print(f"      Provider: {role['provider_id']}")
            if role.get("related_pages"):
                print(f"      📄 Toegang tot pages ({len(role['related_pages'])}): {', '.join(role['related_pages'])}")
            if role.get("related_visualizations"):
                print(f"      🎨 Visualizations ({len(role['related_visualizations'])}):")
                for viz in role["related_visualizations"][:5]:  # Toon eerste 5
                    print(f"         - {viz['app_name']} (op {viz['page']})")
                if len(role['related_visualizations']) > 5:
                    print(f"         ... en {len(role['related_visualizations']) - 5} meer")
            print(f"      ℹ️  {role['note']}")
    
    print("\n" + "="*80)


def main():
    if len(sys.argv) < 2:
        print("Gebruik: python workzone_analyzer.py <zip_file>")
        print("Voorbeeld: python workzone_analyzer.py ContentTransport_20260203_095800.zip")
        sys.exit(1)
    
    zip_file = sys.argv[1]
    
    if not os.path.exists(zip_file):
        print(f"❌ Bestand niet gevonden: {zip_file}")
        sys.exit(1)
    
    # Unzip
    print(f"\n📦 Unzipping {zip_file}...")
    extract_dir = 'extracted_workzone'
    unzip_recursive(zip_file, extract_dir)
    print(f"✓ Bestanden geëxtraheerd naar {extract_dir}/")
    
    # Analyseer
    print("\n📊 Analyseren van Workzone data...")
    data = load_workzone_data(extract_dir)
    overview = analyze_workzone_export(data)
    
    # Print overzicht
    print_overview(overview)
    
    # Sla JSON op
    output_file = 'workzone_overview.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(overview, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Overzicht opgeslagen in: {output_file}")


if __name__ == "__main__":
    main()