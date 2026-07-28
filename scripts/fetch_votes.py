import io
import json
import os
import ssl
import urllib.request
import zipfile

SCRUTINS_ZIP_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
ORGANES_ZIP_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"
DISSOLUTION_DATE = "2024-06-09"

COLOR_PALETTE = {
    "LFI-NFP": {"bg": "#cc0000", "text": "#ffffff"},
    "LFI": {"bg": "#cc0000", "text": "#ffffff"},
    "EPR": {"bg": "#ffb900", "text": "#000000"},
    "RN": {"bg": "#0d2040", "text": "#ffffff"},
    "GDR": {"bg": "#dd2129", "text": "#ffffff"},
    "LIOT": {"bg": "#f39c12", "text": "#ffffff"},
    "EcoS": {"bg": "#00a651", "text": "#ffffff"},
    "ECO": {"bg": "#00a651", "text": "#ffffff"},
    "SOC": {"bg": "#e40046", "text": "#ffffff"},
    "HOR": {"bg": "#00a896", "text": "#ffffff"},
    "DR": {"bg": "#0055a5", "text": "#ffffff"},
    "UDR": {"bg": "#1e3799", "text": "#ffffff"},
    "DEM": {"bg": "#e67e22", "text": "#ffffff"},
    "NI": {"bg": "#718093", "text": "#ffffff"}
}

def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def fetch_official_organs():
    print("Récupération des groupes parlementaires...")
    organs_map = {}
    req = urllib.request.Request(ORGANES_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, context=get_ssl_context(), timeout=60) as resp:
            zip_bytes = resp.read()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                if name.endswith(".json") and "organe" in name:
                    with z.open(name) as f:
                        try:
                            data = json.load(f)
                            organe = data.get("organe", {})
                            if organe.get("codeType") in ["GP", "NI"] and organe.get("uid"):
                                uid = organe.get("uid")
                                libelle = organe.get("libelle")
                                if not libelle or libelle == "undefined": continue
                                short_name = organe.get("libelleAbrev") or uid
                                colors = COLOR_PALETTE.get(short_name, {"bg": "#475569", "text": "#ffffff"})

                                organs_map[uid] = {
                                    "name": libelle.strip(),
                                    "shortName": short_name.strip(),
                                    "bg": colors["bg"],
                                    "text": colors["text"]
                                }
                        except Exception:
                            continue
    except Exception as e:
        print(f"⚠️ Erreur chargement des organes : {e}")

    return organs_map

def process_single_scrutin(data_obj, organs_map):
    scrutin = data_obj.get("scrutin") if isinstance(data_obj, dict) and "scrutin" in data_obj else data_obj
    if not isinstance(scrutin, dict): return None

    date_scrutin = str(scrutin.get("dateScrutin", ""))
    legislature = str(scrutin.get("legislature", ""))
    if not (legislature == "17" or (date_scrutin and date_scrutin >= DISSOLUTION_DATE)):
        return None

    ventilation = scrutin.get("ventilationVotes") or {}
    organe_root = ventilation.get("organe") or {}
    groupes_container = organe_root.get("groupes") or {}
    raw_groups = groupes_container.get("groupe", [])
    if isinstance(raw_groups, dict): raw_groups = [raw_groups]

    groups_detail = []
    for grp in raw_groups:
        if not isinstance(grp, dict): continue
        group_id = str(grp.get("organeRef", ""))
        if group_id not in organs_map: continue
        meta = organs_map[group_id]

        vote_obj = grp.get("vote") or {}
        decompte = vote_obj.get("decompteVoix") or {}

        pour = int(decompte.get("pour") or 0)
        contre = int(decompte.get("contre") or 0)
        abstentions = int(decompte.get("abstentions") or 0) + int(decompte.get("nonVotants") or 0)
        pos_maj = str(vote_obj.get("positionMajoritaire", "")).strip().upper()

        if pos_maj in ["POUR", "CONTRE", "ABSTENTION"]: global_vote = pos_maj
        else:
            if pour >= contre and pour >= abstentions: global_vote = "POUR"
            elif contre >= pour and contre >= abstentions: global_vote = "CONTRE"
            else: global_vote = "ABSTENTION"

        groups_detail.append({
            "id": group_id,
            "name": meta["name"],
            "shortName": meta["shortName"],
            "bg": meta["bg"],
            "text": meta["text"],
            "globalVote": global_vote,
            "votes": {"pour": pour, "contre": contre, "abstention": abstentions}
        })

    if not groups_detail: return None

    num_scrutin = str(scrutin.get("numero", "0"))
    titre = scrutin.get("titre") or scrutin.get("objet") or "Scrutin sans titre"

    return {
        "numero": num_scrutin,
        "titre": titre,
        "date": date_scrutin,
        "url": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{num_scrutin}",
        "groups": groups_detail
    }

def main():
    os.makedirs("data", exist_ok=True)
    organs_map = fetch_official_organs()
    processed_votes = []

    print("Téléchargement des scrutins...")
    req = urllib.request.Request(SCRUTINS_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, context=get_ssl_context(), timeout=60) as resp:
            zip_bytes = resp.read()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for name in z.namelist():
                if name.endswith(".json"):
                    with z.open(name) as f:
                        try:
                            data = json.load(f)
                            res = process_single_scrutin(data, organs_map)
                            if res: processed_votes.append(res)
                        except Exception:
                            continue

        processed_votes.sort(
            key=lambda x: int(x["numero"]) if str(x["numero"]).isdigit() else 0,
            reverse=True
        )

        output_file = "data/votes.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(processed_votes, f, ensure_ascii=False, indent=2)

        print(f"✅ Succès : {len(processed_votes)} scrutins enregistrés dans {output_file}")

    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    main()