import os
import json
import zipfile
import urllib.request
import io

URL_OPEN_DATA = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"

def fetch_and_process_votes():
    print("Téléchargement des données de l'Assemblée nationale...")
    req = urllib.request.Request(URL_OPEN_DATA, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    try:
        with urllib.request.urlopen(req) as response:
            zip_buffer = io.BytesIO(response.read())
    except Exception as e:
        print(f"Erreur lors du téléchargement de l'API : {e}")
        return

    processed_votes = []

    try:
        with zipfile.ZipFile(zip_buffer) as z:
            for filename in z.namelist():
                if filename.endswith('.json'):
                    with z.open(filename) as f:
                        content = json.load(f)
                        data = content.get('scrutin', {})
                        
                        titre = data.get('titre', '')
                        if not titre:
                            continue

                        # Filtre sur les votes généraux
                        if "sur l'ensemble" in titre.lower() or "projet de loi" in titre.lower():
                            groupes_votes = {}
                            ventilation = data.get('ventilationVotes', {}).get('organe', {}).get('groupes', {}).get('groupe', [])
                            
                            if isinstance(ventilation, dict):
                                ventilation = [ventilation]

                            for g in ventilation:
                                code_groupe = g.get('organeRef')
                                vote_stats = g.get('vote', {}).get('decompteVoix', {})
                                p = int(vote_stats.get('pour', 0))
                                c = int(vote_stats.get('contre', 0))
                                a = int(vote_stats.get('abstention', 0))
                                
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
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier ZIP : {e}")
        return

    # Trier par numéro de scrutin (plus récents d'abord)
    processed_votes.sort(key=lambda x: int(x['numero']) if str(x['numero']).isdigit() else 0, reverse=True)
    final_data = processed_votes[:50]

    os.makedirs('data', exist_ok=True)
    with open('data/votes.json', 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
        
    print(f"Succès : {len(final_data)} votes enregistrés dans data/votes.json")

if __name__ == "__main__":
    fetch_and_process_votes()