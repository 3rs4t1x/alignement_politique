import io
import json
import os
import ssl
import urllib.request
import zipfile

# Table de correspondance officielle pour la 17e législature (2024-présent)
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


def get_group_metadata(group_id):
  if group_id in GROUPS_MAPPING:
    return GROUPS_MAPPING[group_id]
  return {
      "name": f"Groupe {group_id}",
      "shortName": "AUTRE",
      "bg": "#6c757d",
      "text": "#ffffff",
  }


def extract_raw_groups(scrutin):
  """Extrait la liste des groupes selon l'arborescence réelle des fichiers Open Data."""
  if not isinstance(scrutin, dict):
    return []

  ventilation = scrutin.get("ventilationVotes")
  if not isinstance(ventilation, dict):
    return []

  organe_root = ventilation.get("organe")
  if not isinstance(organe_root, dict):
    return []

  groupes_container = organe_root.get("groupes")
  if not isinstance(groupes_container, dict):
    return []

  groupes = groupes_container.get("groupe", [])
  if isinstance(groupes, dict):
    return [groupes]
  elif isinstance(groupes, list):
    return groupes

  return []


def process_single_scrutin(data_obj):
  # Unpack racine
  scrutin = (
      data_obj.get("scrutin")
      if isinstance(data_obj, dict) and "scrutin" in data_obj
      else data_obj
  )
  if not isinstance(scrutin, dict):
    return None

  date_scrutin = str(scrutin.get("dateScrutin", ""))
  legislature = str(scrutin.get("legislature", ""))

  is_post_dissolution = legislature == "17" or (
      date_scrutin and date_scrutin >= DISSOLUTION_DATE
  )
  if not is_post_dissolution:
    return None

  raw_groups = extract_raw_groups(scrutin)
  if not raw_groups:
    return None

  groups_detail = []

  for grp in raw_groups:
    if not isinstance(grp, dict):
      continue

    group_id = str(grp.get("organeRef", ""))
    meta = get_group_metadata(group_id)

    vote_obj = grp.get("vote")
    if not isinstance(vote_obj, dict):
      vote_obj = {}

    decompte = vote_obj.get("decompteVoix")
    if not isinstance(decompte, dict):
      decompte = {}

    pour = int(decompte.get("pour") or 0)
    contre = int(decompte.get("contre") or 0)
    abstentions = int(decompte.get("abstentions") or 0)
    non_votants = int(decompte.get("nonVotants") or 0)
    abstention_total = abstentions + non_votants

    pos_maj = str(vote_obj.get("positionMajoritaire", "")).strip().upper()

    if pos_maj in ["POUR", "CONTRE", "ABSTENTION"]:
      global_vote = pos_maj
    else:
      if pour >= contre and pour >= abstention_total:
        global_vote = "POUR"
      elif contre >= pour and contre >= abstention_total:
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
        "votes": {
            "pour": pour,
            "contre": contre,
            "abstention": abstention_total,
        },
    })

  num_scrutin = str(scrutin.get("numero", "0"))
  titre = scrutin.get("titre") or scrutin.get("objet") or "Scrutin sans titre"

  return {
      "numero": num_scrutin,
      "titre": titre,
      "date": date_scrutin,
      "url": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{num_scrutin}",
      "groups": groups_detail,
  }


def main():
  os.makedirs("data", exist_ok=True)
  processed_votes = []

  print(f"Téléchargement de l'archive Open Data...")

  # Contournement des certificats SSL stricts si nécessaire
  ssl_ctx = ssl.create_default_context()
  ssl_ctx.check_hostname = False
  ssl_ctx.verify_mode = ssl.CERT_NONE

  req = urllib.request.Request(
      ZIP_URL,
      headers={
          "User-Agent": (
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          )
      },
  )

  try:
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=60) as resp:
      zip_bytes = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
      for name in z.namelist():
        if name.endswith(".json"):
          with z.open(name) as f:
            try:
              data = json.load(f)
              res = process_single_scrutin(data)
              if res and res.get("groups"):
                processed_votes.append(res)
            except Exception:
              continue

    # Tri du plus récent au plus ancien
    processed_votes.sort(
        key=lambda x: int(x["numero"]) if str(x["numero"]).isdigit() else 0,
        reverse=True,
    )

    output_file = "data/votes.json"
    with open(output_file, "w", encoding="utf-8") as f:
      json.dump(processed_votes, f, ensure_ascii=False, indent=2)

    print(
        f"✅ Succès : {len(processed_votes)} scrutins extraits et enregistrés"
        f" dans {output_file}"
    )

  except Exception as e:
    print(f"❌ Erreur critique pendant l'extraction : {e}")


if __name__ == "__main__":
  main()