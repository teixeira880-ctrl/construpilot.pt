# STAIRPILOT — Guide de build EAS (Android APK / iOS IPA)

Ce guide explique comment générer un APK Android ou un IPA iOS de l'app mobile
STAIRPILOT via **EAS Build** (Expo Application Services). Toutes les commandes
se lancent depuis un ordinateur (Mac ou PC/Linux), pas depuis le pod Emergent.

---

## 1. Prérequis (une seule fois)

### 1.1 Installer Node.js et EAS CLI
```bash
# Vérifier Node ≥ 20
node -v

# Installer eas-cli globalement
npm install -g eas-cli
eas --version    # doit afficher >= 12.0.0
```

### 1.2 Créer un compte Expo
Va sur **https://expo.dev/signup** et crée un compte (gratuit pour les builds
en file d'attente standard). Note bien ton `username`.

### 1.3 Récupérer le code STAIRPILOT
Depuis Emergent : bouton "Save to GitHub" puis clone ton repo :
```bash
git clone <ton-repo-github>
cd <ton-repo>/mobile
```

---

## 2. Initialisation EAS (une seule fois par projet)

```bash
cd mobile
eas login
# entre les creds Expo créés à l'étape 1.2

eas init
# → EAS te propose de créer un projet + génère un projectId
# → il édite automatiquement app.json.extra.eas.projectId
# → il ajoute aussi le champ "owner" dans app.json (ton username Expo)
```

Après `eas init`, commit les changements :
```bash
git add mobile/app.json
git commit -m "chore(eas): init projectId"
```

---

## 3. Générer un APK Android (recommandé pour tester rapidement)

```bash
cd mobile
eas build --platform android --profile preview
```

- EAS met le build en file d'attente (5-15 min sur file gratuite).
- À la fin, tu obtiens :
  - Un lien de téléchargement direct de l'`.apk`
  - Un QR code pour installer sur téléphone Android
  - Une entrée dans **https://expo.dev/accounts/<ton-username>/projects/stairpilot/builds**

Pour installer l'APK sur un Android :
1. Télécharge le fichier `.apk`
2. Sur le téléphone, active "Installer depuis sources inconnues"
3. Ouvre le `.apk` → installation

---

## 4. Générer un IPA iOS

⚠️ iOS nécessite un compte **Apple Developer** (99 USD/an).

```bash
cd mobile
# Simulateur iOS (gratuit, tourne sur Mac uniquement)
eas build --platform ios --profile preview

# App Store / TestFlight (nécessite compte Apple Developer)
eas build --platform ios --profile production
# EAS te demandera tes identifiants Apple et gérera les certificats + profils.
```

Sur Mac : glisse-dépose le `.tar.gz` retourné (contient l'app simulateur) dans
le Simulateur iOS ouvert. Pour un vrai device iOS → TestFlight ou App Store.

---

## 5. Configuration URL backend (IMPORTANT)

Le fichier **`mobile/eas.json`** définit la variable `EXPO_PUBLIC_BACKEND_URL`
qui sera embarquée dans l'app au moment du build. Actuellement elle pointe
vers l'environnement preview Emergent :

```json
"env": {
  "EXPO_PUBLIC_BACKEND_URL": "https://escalier-pro.preview.emergentagent.com"
}
```

### Pour un build de production destiné au Play Store / App Store :

1. Ouvre `mobile/eas.json`
2. Remplace l'URL dans les profils `preview` et `production` par ton backend
   déployé (ex : `https://escalier-pro.emergent.host` si tu utilises le
   déploiement Emergent Publish, ou l'URL de ton serveur si tu as migré vers
   AWS/Railway/Fly.io).
3. Relance `eas build`.

Une build utilise TOUJOURS l'URL qui était dans `eas.json` au moment du build
(pas de hot-reload de l'URL après installation).

---

## 6. Profils disponibles

| Profil | Distribution | Format Android | Usage |
|---|---|---|---|
| `development` | interne | APK dev-client | Développement local avec Expo Go custom |
| `preview` | interne | APK | Test QA / démo client (URL preview) |
| `production` | store | AAB (app-bundle) | Publication Play Store / App Store |

Choisis avec `--profile <name>` sur la commande `eas build`.

---

## 7. Versioning

- `app.json` : `version` (semver, ex "1.0.1") — affichée à l'utilisateur
- `app.json` : `ios.buildNumber` / `android.versionCode` — auto-incrémentés
  par EAS grâce à `"appVersionSource": "remote"` dans `eas.json`

Pour bumper la version affichée :
```bash
# édite app.json → "version": "1.0.1"
git commit -am "chore: bump version 1.0.1"
eas build --platform android --profile production
```

---

## 8. Dépannage courant

| Symptôme | Solution |
|---|---|
| `Error: Invalid project ID` | Relance `eas init` |
| `Bundle identifier already taken` | Change `ios.bundleIdentifier` dans `app.json` (mets `com.<ton-nom>.stairpilot`) |
| `Google Play package name already used` | Idem avec `android.package` |
| App crashe au démarrage avec "Network Error" | Vérifie que `EXPO_PUBLIC_BACKEND_URL` dans `eas.json` pointe vers un backend accessible depuis Internet |
| Build succeeds mais l'API ne répond pas | Backend probablement en `localhost:8001` — non joignable depuis un vrai device |

---

## 9. Ressources

- Doc EAS Build : https://docs.expo.dev/build/introduction/
- Prix et files d'attente : https://expo.dev/pricing
- Console EAS : https://expo.dev/accounts/<username>/projects/stairpilot

---

Généré pour STAIRPILOT — Expo SDK 57 · React Native 0.86 · EAS >= 12.
