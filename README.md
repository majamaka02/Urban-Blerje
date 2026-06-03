# Menaxhimi i Stokut - PWA Version 2.0

Aplikacion modern për menaxhimin e stokut dhe porositeve të materialeve me suport të plotë PWA.

## Veçoritë e Reja

### 📱 PWA (Progressive Web App)
- **Instalo në Home Screen**: Në iPhone ose Android, hap aplikacionin dhe shko në Menu → "Add to Home Screen"
- **Punon Offline**: Aplikacioni funksionon edhe pa internetim (i limituar)
- **Përvojë Desktop-like**: Lancimet si aplikacion lokal, jo si faqe web

### 🎨 UI/UX Përmirësimet
- **Responsive Design**: Optimizuar për Desktop, Tablet, dhe Mobile
- **Bottom Navigation Mobile**: Në telefon, navigimi është në fund të ekranit
- **Touch Optimized**: Butona dhe inpute të dimensionit të duhur për prekje
- **Dark Mode**: Suporton dark mode sistem
- **Animacione**: Tranzicione të qetë dhe interaksione

### 📄 PDF Eksport i Përmirësuar
- **Top Section**: Informacioni i departamentit dhe data
- **Client Info**: Detajet e klientit (emri, kategoria, data regjistrimi)
- **Materials Section**: Lista e materialeve që duhen blerë për secilin klient
- **Summary Table**: Permbledhja ose lista e plotë e porositeve

### 🎯 Logo Integration
- Logoja "URBAN DECOR" shfaqet në sidebar header
- Icons PWA me temën e markës

## Si të Instalosh PWA

### iOS (iPhone/iPad)
1. Hap aplikacionin në Safari
2. Prek ikonën "Share" (lart djathtas)
3. Scroll down dhe shko te "Add to Home Screen"
4. Emri dhe prek "Add"
5. Aplikacioni do t'ju shfaqet në home screen

### Android
1. Hap aplikacionin në Chrome/Firefox
2. Prek menu-n (3 pika në këndin e sipër djathtas)
3. Shko te "Install app" ose "Add to Home Screen"
4. Prek "Install"
5. Aplikacioni installohet si PWA

### Desktop
- Chrome/Edge: Prek ikonën e instalimit në address bar
- Shfaqet si aplikacion standalone (pa browser UI)

## Përdorimi

### Shto Kategori (Klient)
1. Shko te "Krijo Kategoritë"
2. Emri i klientit dhe kategoria
3. Shto ri

### Shto Porosi
1. Shgo në departament (Iverica, Ngjyra, Druri, Shtofi)
2. Zgjidh klient
3. Zgjidh material, sasi, shënim
4. Shto porosi

### Eksporto në PDF
1. Shko në departament
2. Prek "Eksporto PDF"
3. Zgjidh mënyrën: "Summary" ose "Items"
4. Zgjidh klient (opsionale)
5. PDF do të përfshijë:
   - Header me info departamenti
   - Info klienti (nëse filtro)
   - Materialet që duhen blerë (me sasi)
   - Tabela e përgjithshme

## Teknologjia

- **Backend**: Flask + SQLAlchemy
- **Frontend**: HTML5, CSS3, JavaScript
- **PWA**: Service Worker, Web App Manifest
- **PDF**: ReportLab
- **Database**: SQLite

## Kërkesat

```
Flask>=3.0
Flask-SQLAlchemy>=3.0
openpyxl
reportlab
gunicorn
Pillow (për zyrrat e PWA)
```

## Instalim Lokal

```bash
# Clone repository
cd "Menaxhim i blejres v2.0 PWA"

# Krijo virtual environment
python -m venv .venv

# Aktivizo environment
.venv\Scripts\activate

# Instalo paketa
pip install -r requirements.txt

# Xhiro aplikacionin
python app.py
```

Aplikacioni do të jetë i disponueshëm në: `http://localhost:5000`

## Kredenciale Default

| Përdoruesi | Password | Roli |
|-----------|----------|------|
| admin | 123 | Superadmin |
| Altin | 123 | User |

⚠️ **Ndreqe fjalëkalimet në produksion!**

## Skin-i i Aplikacionit

- Sidebar (Dark Theme): `#1e293b`
- Primary Color: `#3b82f6` (Blue)
- Success Color: `#10b981` (Green)
- Background: `#f4f6f9` (Light)

## Tips për Mobile

- Prek ikonën "+" në fund për shto porosi
- Swipe djathtas/majtas për navigim
- Prek material për më shumë info
- Butoni "✓" për marko si blerë
- Prek ikonën trash për fshij

---

**Version**: 2.0 PWA Edition
**Gjuhë**: Shqip (Albanian)
**Support**: Urban Decor Management System
