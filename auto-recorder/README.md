# auto-recorder — enregistrer un webinaire sans être devant l'ordinateur

Windows · OBS Studio · Meet / Teams / Zoom (en tant que participant).

Le script (1) contrôle que tout est prêt, (2) rejoint la réunion, (3) lance OBS,
(4) surveille son, fichier et réseau pendant la séance, (5) arrête et vous notifie.

> **Statut : prototype.** La logique de surveillance est testée (`tests/`). Le dialogue
> avec OBS et le module `joiner.py` n'ont **pas** été éprouvés contre un vrai OBS ni de
> vraies plateformes. Faire une réunion de test (Meet à soi-même suffit) avant un événement réel.

## Installation (une fois)

1. Python 3.11+ ; `pip install -r requirements.txt` ; `playwright install chromium` (pour `--join`).
2. OBS ≥ 28 : *Outils > Paramètres du serveur WebSocket* → activer, définir un mot de passe.
3. **Importer la configuration OBS fournie** (dossier `obs-config/`) :
   - *Collection de scènes > Importer* → `obs-config/Webinaire.scene-collection.json`, puis
     *Collection de scènes > Webinaire*. Elle contient la scène « Webinaire » avec :
     - « Capture fenêtre navigateur » : fenêtre `chrome.exe` (Windows Graphics Capture, sans curseur) ;
     - « Capture écran (secours) » : masquée ; l'afficher (œil) si la capture de fenêtre reste noire ;
     - « Audio navigateur » : *Capture audio d'application* sur `chrome.exe` (uniquement le son
       du navigateur, pas vos notifications Windows). Aucun micro ni « Audio du bureau » n'est
       ajouté : vous ne parlez pas, et rien d'autre ne doit fuiter dans l'enregistrement.
   - *Profil > Importer* → dossier `obs-config/profile/Webinaire` (1080p, 25 i/s, x264,
     qualité « Small », format MKV). Choisir ensuite le dossier d'enregistrement dans
     *Paramètres > Sortie*.
   - *Paramètres > Avancé > Remux automatique en mp4* : à cocher si vous voulez du mp4 (le MKV
     reste intact en cas de plantage d'OBS ; le script annonce le chemin du fichier brut).
   - **À vérifier une fois** : lancer une réunion de test avec `--join`, regarder si la source de
     fenêtre affiche l'image et si le vumètre de « Audio navigateur » bouge. Si la fenêtre est
     introuvable, double-cliquer la source et la re-sélectionner dans la liste. Si le navigateur
     capturé n'est pas Chrome (Edge : `msedge.exe`), ajuster aussi l'audio.
   - Prérequis : OBS ≥ 29 (la capture audio d'application est absente des versions plus anciennes).
4. `copy config.example.toml config.toml` puis renseigner mot de passe, noms de scène/source,
   et éventuellement `ntfy_topic` pour les alertes sur téléphone (app ntfy).

## Utilisation

```
python recorder.py --url "https://meet.google.com/abc-defg-hij" --duration 90 --join
```

- `--duration` : durée maximale en minutes (arrêt de sécurité).
- `--join` : rejoint via un Chromium dédié (profil persistant `browser-profile/`). Sans cette
  option, le lien est ouvert dans votre navigateur par défaut et vous cliquez vous-même.
- **Première fois** : lancer une réunion de test avec `--join`, et si une plateforme demande
  une connexion (Teams, Zoom avec authentification, Meet restreint à une organisation), la
  faire une fois à la main dans la fenêtre : le profil est conservé.

## Ce qui est contrôlé

| Contrôle | Quand | Réaction |
|---|---|---|
| Scène et source audio existent, Internet joignable, latence | avant | abandon + alerte |
| OBS enregistre toujours | toutes les 10 s | relance + alerte |
| Taille du fichier croît | toutes les 10 s | alerte si figé > 45 s |
| Niveau audio > seuil | en continu | alerte si silence > 60 s |
| Silence > 15 min après avoir entendu du son | en continu | arrêt auto (fin de séance probable) |
| Latence réseau | toutes les 10 s | alerte (perdue / lente) |

Les seuils sont dans `config.toml`. Une alerte « Pas de son » peut être légitime (pause
de l'intervenant) : elle informe, elle n'arrête rien.

## Planifier (Planificateur de tâches Windows)

```
schtasks /Create /TN "Webinaire-2026-10-21" /SC ONCE /SD 21/10/2026 /ST 13:55 ^
  /TR "python C:\chemin\auto-recorder\recorder.py --url https://... --duration 100 --join" ^
  /RU %USERNAME%
```
(format de date selon les paramètres régionaux ; sinon utiliser l'interface graphique).

Prérequis pour que cela fonctionne **sans vous** :
- exécuter la tâche *« uniquement si l'utilisateur est connecté »* (OBS et le navigateur ont
  besoin d'une session de bureau) ;
- désactiver la mise en veille et le verrouillage automatique de l'écran ;
- OBS peut être lancé avant par une seconde tâche, ou ouvert en permanence ;
- laisser l'ordinateur sur secteur.

## Limites connues

- **Salle d'attente / lobby** : un participant admis manuellement par l'organisateur ne sera
  pas admis si personne ne l'accepte. Prévenir l'organisateur ou prévoir un lien direct.
- **Webinaires avec inscription** (Zoom, Teams Live) : lien personnel et parfois client natif
  obligatoire ; le client web peut être désactivé par l'organisateur.
- **Interfaces mouvantes** : les libellés de boutons de `joiner.py` sont à ajuster ; une capture
  `logs/join-failure.png` aide au diagnostic.
- **Cadre juridique** : informer/obtenir l'accord de l'organisateur et des intervenants avant
  d'enregistrer une séance dont vous n'êtes pas l'hôte (conditions d'utilisation, droit à
  l'image, RGPD, droit d'auteur).
- Le sujet `ntfy` n'est protégé que par son nom : le choisir long et aléatoire, sans contenu sensible.
