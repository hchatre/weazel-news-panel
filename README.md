# qb-weazel-ui

**Weazel News Panel for QBCore**  
Un panneau complet pour les journalistes : articles, dossiers, likes, commentaires, administration.

## Fonctionnalités

- Articles (brouillons, en attente, publiés)
- Likes et commentaires (limite 150 caractères)
- Dossiers d'enquête avec timeline (rumeurs, confirmations, démentis)
- Notifications d'articles publiés
- Administration : recrutement, changement de grade, licenciement
- Upload d'images via **lb-upload** (ou système d'URL discord manuel)

## Dépendances

- `qb-core`
- `oxmysql`
- `lb-upload` (optionnel pour l'upload d'images)

## Installation

1. Téléchargez la ressource et placez-la dans votre dossier `resources`.
2. Importez le fichier `sql/install.sql` dans votre base de données.
3. (Optionnel) Configurez `server/main.lua` avec votre clé API lb-upload.
4. Ajoutez `ensure qb-weazel-ui` dans votre `server.cfg`.

## Utilisation

- Commande : `/weazel` (accessible uniquement au job `reporter`)
- Les permissions sont basées sur les grades du job `reporter` (0‑3).

## Configuration

Dans `server/main.lua` :

```lua
local LB_UPLOAD_URL = "http://127.0.0.1:4200/upload"   -- URL de lb-upload
local LB_UPLOAD_API_KEY = "votre_clé_api"              -- Clé pour lb-upload