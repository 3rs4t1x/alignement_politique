import io
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import zipfile

SCRUTINS_ZIP_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
ORGANES_ZIP_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/amo/deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"

DISSOLUTION_DATE = "2024-06-09"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Réglages Gemini ---------------------------------------------------
# NB : si Google déprécie ce modèle, la liste à jour est ici :
# https://ai.google.dev/gemini-api/docs/deprecations
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MAX_RETRIES = 3          # tentatives en cas de dépassement de quota (HTTP 429)
GEMINI_RETRY_DELAY = 20         # secondes d'attente avant de retenter après un 429
GEMINI_CALL_DELAY = 4.5         # secondes entre deux appels réussis, pour rester sous le quota gratuit (~10-15 req/min)
MAX_NEW_SUMMARIES_PER_RUN = 200 # évite d'épuiser le quota gratuit journalier (~500 req/jour) en un seul run
# -------------------------------------------------------------------------

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

def get_insecure_ssl_context():
    """Contexte SSL sans vérification de certificat.

    Utilisé UNIQUEMENT pour data.assemblee-nationale.fr, dont la chaîne de
    certificats est historiquement capricieuse. Ne jamais utiliser ce
    contexte pour un appel transportant une clé API (voir generate_ai_summary),
    car cela expose la clé à une attaque de type "man-in-the-middle".
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def generate_ai_summary(titre):
    """Interroge Gemini pour générer une synthèse neutre et structurée du texte.

    Retourne None en cas d'échec définitif (clé invalide, texte non parsable, etc.)
    et réessaie automatiquement en cas de dépassement de quota (HTTP 429).
    """
    if not GEMINI_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

    prompt = f"""
Tu es un assistant parlementaire rigoureusement neutre et pédagogique.
Analyse cet intitulé de scrutin de l'Assemblée nationale française :
"{titre}"

Fournis une explication impartiale et accessible au grand public sous forme d'un objet JSON strict respectant cette structure exacte :
{{
  "contexte": "2 à 3 phrases simples expliquant l'objectif concret du texte et le problème qu'il cherche à résoudre.",
  "opportunites": ["Argument principal ou bénéfice attendu 1", "Argument principal ou bénéfice attendu 2"],
  "risques": ["Critique principale ou risque identifié 1", "Critique principale ou risque identifié 2"]
}}
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.3,
            "maxOutputTokens": 1024
        }
    }

    for attempt in range(1, GEMINI_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    # Méthode recommandée par Google (ai.google.dev/gemini-api/docs/api-key) :
                    # l'en-tête x-goog-api-key est préféré à l'ancien paramètre d'URL "?key=...",
                    # qui expose la clé dans les logs serveur et les outils intermédiaires.
                    "x-goog-api-key": GEMINI_API_KEY,
                }
            )
            # Contexte SSL par défaut (vérifié) : on n'utilise JAMAIS le contexte
            # non sécurisé ici, puisque la requête transporte la clé API.
            with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=20) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_response)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"⏳ Quota Gemini atteint pour '{titre[:30]}...' (tentative {attempt}/{GEMINI_MAX_RETRIES}), nouvel essai dans {GEMINI_RETRY_DELAY}s")
                time.sleep(GEMINI_RETRY_DELAY)
                continue
            elif e.code in (401, 403):
                # Depuis le 19 juin 2026, Google refuse les clés Gemini qui n'ont pas
                # de restriction d'API configurée. Si cette erreur apparaît alors que
                # la clé fonctionnait auparavant, il faut la restreindre à
                # "Generative Language API" dans Google Cloud Console > Identifiants,
                # ou en générer une nouvelle depuis Google AI Studio.
                print(f"❌ Clé API Gemini refusée (HTTP {e.code}) pour '{titre[:30]}...' : {e}")
                return None
            else:
                print(f"⚠️ Erreur HTTP Gemini ({e.code}) pour '{titre[:30]}...': {e}")
                return None
        except Exception as e:
            print(f"⚠️ Erreur génération Gemini pour '{titre[:30]}...': {e}")
            return None

    print(f"❌ Abandon pour '{titre[:30]}...' après {GEMINI_MAX_RETRIES} tentatives (quota toujours dépassé).")
    return None

def fetch_official_organs():
    print("Récupération des groupes parlementaires officiels...")
    organs_map = {}
    req = urllib.request.Request(ORGANES_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, context=get_insecure_ssl_context(), timeout=60) as resp:
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
        print(f"⚠️ Impossible de charger le référentiel des organes ({e}).")

    return organs_map

def extract_raw_groups(scrutin):
    if not isinstance(scrutin, dict): return []
    ventilation = scrutin.get("ventilationVotes")
    if not isinstance(ventilation, dict): return []
    organe_root = ventilation.get("organe")
    if not isinstance(organe_root, dict): return []
    groupes_container = organe_root.get("groupes")
    if not isinstance(groupes_container, dict): return []
    groupes = groupes_container.get("groupe", [])
    return [groupes] if isinstance(groupes, dict) else (groupes if isinstance(groupes, list) else [])

def process_single_scrutin(data_obj, organs_map, existing_cache, allow_ai=True):
    """Traite un scrutin. Retourne un dict avec une clé interne '_new_ai_call'
    indiquant si un appel Gemini a réellement été effectué (utile pour le
    throttling et le comptage de quota côté appelant)."""
    scrutin = data_obj.get("scrutin") if isinstance(data_obj, dict) and "scrutin" in data_obj else data_obj
    if not isinstance(scrutin, dict): return None

    date_scrutin = str(scrutin.get("dateScrutin", ""))
    legislature = str(scrutin.get("legislature", ""))
    if not (legislature == "17" or (date_scrutin and date_scrutin >= DISSOLUTION_DATE)):
        return None

    raw_groups = extract_raw_groups(scrutin)
    if not raw_groups: return None

    groups_detail = []
    for grp in raw_groups:
        if not isinstance(grp, dict): continue
        group_id = str(grp.get("organeRef", ""))
        if group_id not in organs_map: continue
        meta = organs_map[group_id]

        vote_obj = grp.get("vote") if isinstance(grp.get("vote"), dict) else {}
        decompte = vote_obj.get("decompteVoix") if isinstance(vote_obj.get("decompteVoix"), dict) else {}

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

    # Récupération de l'explication IA (depuis le cache ou génération)
    cached_entry = existing_cache.get(num_scrutin, {})
    ai_summary = cached_entry.get("aiSummary")
    made_new_call = False
    if not ai_summary and GEMINI_API_KEY and allow_ai:
        print(f"🤖 Génération de la synthèse Gemini pour le scrutin n°{num_scrutin}...")
        ai_summary = generate_ai_summary(titre)
        made_new_call = True

    return {
        "numero": num_scrutin,
        "titre": titre,
        "date": date_scrutin,
        "url": f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{num_scrutin}",
        "aiSummary": ai_summary,
        "groups": groups_detail,
        "_new_ai_call": made_new_call
    }

def main():
    os.makedirs("data", exist_ok=True)
    output_file = "data/votes.json"

    # Chargement du cache existant pour économiser les appels API Gemini
    existing_cache = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                existing_cache = {v["numero"]: v for v in old_data if "numero" in v}
        except Exception:
            pass

    organs_map = fetch_official_organs()
    processed_votes = []
    new_ai_calls = 0

    def save_progress():
        """Sauvegarde immédiatement ce qui a été traité jusqu'ici.
        Appelée régulièrement et systématiquement en cas d'erreur, pour ne
        jamais perdre les synthèses Gemini déjà générées (et donc déjà
        payées en quota) si le run est interrompu en cours de route."""
        if not processed_votes:
            return
        sorted_votes = sorted(
            processed_votes,
            key=lambda x: int(x["numero"]) if str(x["numero"]).isdigit() else 0,
            reverse=True
        )
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sorted_votes, f, ensure_ascii=False, indent=2)

    print("Téléchargement des scrutins...")
    req = urllib.request.Request(SCRUTINS_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, context=get_insecure_ssl_context(), timeout=60) as resp:
            zip_bytes = resp.read()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            names = [n for n in z.namelist() if n.endswith(".json")]

            for i, name in enumerate(names):
                with z.open(name) as f:
                    try:
                        data = json.load(f)
                        allow_ai = bool(GEMINI_API_KEY) and new_ai_calls < MAX_NEW_SUMMARIES_PER_RUN
                        res = process_single_scrutin(data, organs_map, existing_cache, allow_ai=allow_ai)
                        if res and res.get("groups"):
                            if res.pop("_new_ai_call", False):
                                new_ai_calls += 1
                                time.sleep(GEMINI_CALL_DELAY)  # respecte le quota du tier gratuit
                            processed_votes.append(res)
                    except Exception as e:
                        print(f"⚠️ Scrutin ignoré ({name}): {e}")
                        continue

                # Checkpoint : on sauvegarde régulièrement pour ne rien perdre
                # si le job est interrompu (timeout GitHub Actions, coupure réseau, etc.)
                if (i + 1) % 50 == 0:
                    save_progress()

        save_progress()
        print(f"✅ Succès : {len(processed_votes)} scrutins enregistrés dans {output_file} "
              f"({new_ai_calls} nouvelle(s) synthèse(s) Gemini générée(s))")

    except Exception as e:
        print(f"❌ Erreur critique : {e}")
        save_progress()  # on conserve malgré tout tout ce qui a pu être traité avant l'erreur

if __name__ == "__main__":
    main()
