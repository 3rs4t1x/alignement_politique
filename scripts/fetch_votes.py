import os
import json
import zipfile
import urllib.request
import io

# URL Open Data de l'Assemblée Nationale (Législature courante)
URL_OPEN_DATA = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"

def fetch_and_process_votes():
    print("Téléchargement des données de l'Assemblée nationale...")
    req = urllib.request.Request(URL_OPEN_DATA, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req) as response:
        zip_buffer = io.BytesIO(response.read())

    processed_votes = []

    with zipfile.ZipFile(zip_buffer) as z:
        for filename in z.namelist():
            if filename.endswith('.json'):
                with z.open(filename) as f:
                    data = json.load(f)['scrutin']
                    
                    titre = data.get('titre', '')
                    # Filtrer pour ne garder prioritairement que les votes "sur l'ensemble" d'un texte
                    # (plus simples à comprendre qu'un amendement technique)
                    if "sur l'ensemble" in titre.lower() or "projet de loi" in titre.lower():
                        
                        # Extraire le vote majoritaire de chaque groupe politique
                        groupes_votes = {}
                        ventilations = data.get('ventilationVotes', {}).get('organe', {}).get('groupes', {}).get('groupe', [])
                        
                        if isinstance(ventilations, dict):
                            ventilations = [ventilations]

                        for g in ventilations:
                            code_groupe = g.get('organeRef')
                            # Décompte des voix
                            vote_stats = g.get('vote', {}).get('decompteVoix', {})
                            p = int(vote_stats.get('pour', 0))
                            c = int(vote_stats.get('contre', 0))
                            a = int(vote_stats.get('abstention', 0))
                            
                            # Position retenue pour le groupe = la majorité interne
                            position = "POUR" if p > max(c, a) else ("CONTRE" if c > max(p, a) else "ABSTENTION")
                            groupes_votes[code_groupe] = position

                        processed_votes.append({
                            "id": data.get('uid'),
                            "numero": data.get('numero'),
                            "date": data.get('dateScrutin'),
                            "titre": titre,
                            "url": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{data.get('numero')}",
                            "groupes": groupes_votes
                        })

    # Trier par date (du plus récent au plus ancien) et limiter aux 50 derniers
    processed_votes.sort(key=lambda x: x['numero'], reverse=True)
    final_data = processed_votes[:50]

    os.makedirs('data', exist_ok=True)
    with open('data/votes.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
        
    print(f"Succès : {len(final_data)} votes enregistrés dans data/votes.json")

if __name__ == "__main__":
    fetch_and_process_votes()