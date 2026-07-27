import json
import os
from datetime import datetime

# Table de correspondance complète pour la 17e législature (post-dissolution 2024)
GROUPS_MAPPING = {
    "PO845401": {"name": "La France insoumise - NFP", "shortName": "LFI", "bg": "#cc0000", "text": "#ffffff"},
    "PO845407": {"name": "Ensemble pour la République", "shortName": "EPR", "bg": "#ffb900", "text": "#000000"},
    "PO845413": {"name": "Rassemblement National", "shortName": "RN", "bg": "#0d2040", "text": "#ffffff"},
    "PO845419": {"name": "Gauche Démocrate et Républicaine", "shortName": "GDR", "bg": "#dd2129", "text": "#ffffff"},
    "PO845425": {"name": "Libertés, Indépendance, Outre-mer et Territoires", "shortName": "LIOT", "bg": "#f39c12", "text": "#ffffff"},
    "PO845439": {"name": "Écologiste et Social", "shortName": "ECO", "bg": "#00a651", "text": "#ffffff"},
    "PO845454": {"name": "Socialistes et apparentés", "shortName": "SOC", "bg": "#e40046", "text": "#ffffff"},
    "PO845470": {"name": "Horizons & Indépendants", "shortName": "HOR", "bg": "#00a896", "text": "#ffffff"},
    "PO84585": {"name": "Droite Républicaine", "shortName": "DR", "bg": "#0055a5", "text": "#ffffff"},
    "PO845514": {"name": "Union des Droites pour la République", "shortName": "UDR", "bg": "#1e3799", "text": "#ffffff"},
    "PO872880": {"name": "Les Démocrates", "shortName": "DEM", "bg": "#e67e22", "text": "#ffffff"},
    "PO840056": {"name": "Non-inscrits", "shortName": "NI", "bg": "#718093", "text": "#ffffff"}
}

DISSOLUTION_DATE = "2024-06-09"

def get_group_metadata(group_id, raw_name=""):
    """Récupère le nom lisible et les couleurs d'un groupe parlementaire."""
    if group_id in GROUPS_MAPPING:
        return GROUPS_MAPPING[group_id]
    return {
        "name": raw_name if raw_name else f"Groupe {group_id}",
        "shortName": "AUTRE",
        "bg": "#6c757d",
        "text": "#ffffff"
    }

def process_votes_data(raw_scrutins_list):
    """
    Filtre et formate tous les scrutins depuis la dernière dissolution (17e législature).
    """
    processed_votes = []

    for scrutin in raw_scrutins_list:
        date_scrutin = scrutin.get('dateScrutin', '')
        legislature = str(scrutin.get('legislature', ''))

        is_post_dissolution = (
            legislature == "17" or 
            (date_scrutin and date_scrutin >= DISSOLUTION_DATE)
        )

        if not is_post_dissolution:
            continue

        groups_detail = []
        raw_groups = scrutin.get('ventilationVotes', {}).get('organes', [])
        
        if isinstance(raw_groups, dict):
            raw_groups = [raw_groups]

        for grp in raw_groups:
            group_id = grp.get('organeRef', '')
            meta = get_group_metadata(group_id, grp.get('libelle', ''))
            
            votes_count = {
                'pour': int(grp.get('pour', 0)),
                'contre': int(grp.get('contre', 0)),
                'abstention': int(grp.get('nonVotants', 0)) + int(grp.get('abstentions', 0))
            }

            if votes_count['pour'] >= votes_count['contre'] and votes_count['pour'] >= votes_count['abstention']:
                global_vote = "POUR"
            elif votes_count['contre'] >= votes_count['pour'] and votes_count['contre'] >= votes_count['abstention']:
                global_vote = "CONTRE"
            else:
                global_vote = "ABSTENTION"

            groups_detail.append({
                "id": group_id,
                "name": meta["name"],
                "shortName": meta["shortName"],
                "bg": meta["bg"],
                "text": meta["text"],
                "globalVote": global_vote,
                "votes": votes_count
            })

        num_scrutin = str(scrutin.get('numero', '0'))

        processed_votes.append({
            "numero": num_scrutin,
            "titre": scrutin.get('titre', 'Scrutin sans titre'),
            "date": date_scrutin,
            "url": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{num_scrutin}",
            "groups": groups_detail
        })

    processed_votes.sort(
        key=lambda x: int(x['numero']) if str(x['numero']).isdigit() else 0, 
        reverse=True
    )

    return processed_votes

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    raw_data = []
    
    if os.path.exists("data/raw_scrutins.json"):
        with open("data/raw_scrutins.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
    output_data = process_votes_data(raw_data)
    
    with open("data/votes.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)