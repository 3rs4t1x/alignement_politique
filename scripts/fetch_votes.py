import io
import json
import os
import urllib.request
import zipfile

# Table de correspondance officielle pour la 17e législature (post-dissolution 2024)
GROUPS_MAPPING = {
    "PO845401": {
        "name": "La France insoumise - NFP",
        "shortName": "LFI",
        "bg": "#cc0000",
        "text": "#ffffff",
    },
    "PO845407": {
        "name": "Ensemble pour la République",
        "shortName": "EPR",
        "bg": "#ffb900",
        "text": "#000000",
    },
    "PO845413": {
        "name": "Rassemblement National",
        "shortName": "RN",
        "bg": "#0d2040",
        "text": "#ffffff",
    },
    "PO845419": {
        "name": "Gauche Démocrate et Républicaine",
        "shortName": "GDR",
        "bg": "#dd2129",
        "text": "#ffffff",
    },
    "PO845425": {
        "name": "Libertés, Indépendance, Outre-mer et Territoires",
        "shortName": "LIOT",
        "bg": "#f39c12",
        "text": "#ffffff",
    },
    "PO845439": {
        "name": "Écologiste et Social",
        "shortName": "ECO",
        "bg": "#00a651",
        "text": "#ffffff",
    },
    "PO845454": {
        "name": "Socialistes et apparentés",
        "shortName": "SOC",
        "bg": "#e40046",
        "text": "#ffffff",
    },
    "PO845470": {
        "name": "Horizons & Indépendants",
        "shortName": "HOR",
        "bg": "#00a896",
        "text": "#ffffff",
    },
    "PO845485": {
        "name": "Droite Républicaine",
        "shortName": "DR",
        "bg": "#0055a5",
        "text": "#ffffff",
    },
    "PO845514": {
        "name": "Union des Droites pour la République",
        "shortName": "UDR",
        "bg": "#1e3799",
        "text": "#ffffff",
    },
    "PO872880": {
        "name": "Les Démocrates",
        "shortName": "DEM",
        "bg": "#e67e22",
        "text": "#ffffff",
    },
    "PO840056": {
        "name": "Non-inscrits",
        "shortName": "NI",
        "bg": "#718093",
        "text": "#ffffff",
    },
}

DISSOLUTION_DATE = "2024-06-09"
ZIP_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"


def get_group_metadata(group_id, raw_name=""):
  if group_id in GROUPS_MAPPING:
    return GROUPS_MAPPING[group_id]
  return {
      "name": raw_name if raw_name else f"Groupe {group_id}",
      "shortName": "AUTRE",
      "bg": "#6c757d",
      "text": "#ffffff",
  }


def extract_raw_groups(scrutin):
  """Extrait la liste des groupes parlementaires du JSON d'un scrutin."""
  ventilation = scrutin.get("ventilationVotes", {})
  if not ventilation:
    return []

  organe_root = ventilation.get("organe", {})
  if isinstance(organe_root, dict):
    organes_container = organe_root.get("organes", {})
    if isinstance(organes_container, dict):
      organes = organes_container.get("organe", [])
      if isinstance(organes, list):
        return organes
      elif isinstance(organes, dict):
        return [organes]

  raw_organes = ventilation.get("organes", [])
  if isinstance(raw_organes, list):
    return raw_organes
  elif isinstance(raw_organes, dict):
    return [raw_organes]

  return []


def process_single_scrutin(scrutin):
  """Traite un fichier JSON de scrutin individuel."""
  if "scrutin" in scrutin and isinstance(scrutin["scrutin"], dict):
    scrutin = scrutin["scrutin"]

  date_scrutin = str(scrutin.get("dateScrutin", ""))
  legislature = str(scrutin.get("legislature", ""))

  is_post_dissolution = legislature == "17" or (
      date_scrutin and date_scrutin >= DISSOLUTION_DATE
  )
  if not is_post_dissolution:
    return None

  raw_groups = extract_raw_groups(scrutin)
  groups_detail = []

  for grp in raw_groups:
    group_id = grp.get("organeRef", "")
    libelle = grp.get("libelle", "")
    meta = get_group_metadata(group_id, libelle)

    vote_obj = grp.get("vote", {})
    decompte = (
        vote_obj.get("decompteVoix", {})
        if isinstance(vote_obj, dict)
        else {}
    )

    pour = int(
        grp.get("pour")
        or decompte.get("pour")
        or (vote_obj.get("decomptePour") if isinstance(vote_obj, dict) else 0)
        or 0
    )
    contre = int(
        grp.get("contre")
        or decompte.get("contre")
        or (
            vote_obj.get("decompteContre") if isinstance(vote_obj, dict) else 0
        )
        or 0
    )
    abstention = int(
        grp.get("nonVotants") or decompte.get("nonVotants") or 0
    ) + int(grp.get("abstentions") or decompte.get("abstentions") or 0)

    pos_maj = (
        vote_obj.get("positionMajoritaire", "")
        if isinstance(vote_obj, dict)
        else ""
    )
    if pos_maj:
      global_vote = pos_maj.upper()
    else:
      if pour >= contre and pour >= abstention:
        global_vote = "POUR"
      elif contre >= pour and contre >= abstention:
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
        "votes": {"pour": pour, "contre": contre, "abstention": abstention},
    })

  num_scrutin = str(scrutin.get("numero", "0"))
  titre = scrutin.get("titre") or "Scrutin sans titre"

  return {
      "numero": num_scrutin,
      "titre": titre,
      "date": date_scrutin,
      "url": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{num_scrutin}",
      "groups": groups_detail,
  }


def fetch_from_open_data():
  """Télécharge l'archive officielle depuis data.assemblee-nationale.fr"""
  print(f"Téléchargement depuis {ZIP_URL}...")
  req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})

  with urllib.request.urlopen(req, timeout=60) as response:
    zip_data = response.read()

  scrutins_list = []
  with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
    for filename in z.namelist():
      if filename.endswith(".json"):
        with z.open(filename) as f:
          try:
            data = json.load(f)
            processed = process_single_scrutin(data)
            if processed and processed.get("groups"):
              scrutins_list.append(processed)
          except Exception:
            continue
  return scrutins_list


def main():
  os.makedirs("data", exist_ok=True)
  processed_votes = []

  try:
    processed_votes = fetch_from_open_data()
    print(
        f"Succès : {len(processed_votes)} scrutins récupérés via l'Open Data."
    )
  except Exception as e:
    print(f"Erreur lors du téléchargement : {e}")

  # Tri du plus récent au plus ancien
  processed_votes.sort(
      key=lambda x: int(x["numero"]) if str(x["numero"]).isdigit() else 0,
      reverse=True,
  )

  output_path = "data/votes.json"
  with open(output_path, "w", encoding="utf-8") as f:
    json.dump(processed_votes, f, ensure_ascii=False, indent=2)

  print(f"Fichier sauvegardé dans {output_path}")


if __name__ == "__main__":
  main()