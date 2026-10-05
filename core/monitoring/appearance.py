# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/monitoring/appearance.py
# Description : Browser-local wallpaper preferences, independent of canonical memory.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Browser-local wallpaper preferences, independent of canonical memory."""
import base64
from hashlib import sha256

SCRIPT = r"""(() => {
const key = 'eidolon-wallpaper-v1';
const image = document.getElementById('wallpaper-file');
const shade = document.getElementById('wallpaper-shade');
const message = document.getElementById('wallpaper-message');
let settings = {image: '', shade: 75};
const maxDataLength = 1900000;
try { const saved = JSON.parse(localStorage.getItem(key));
 if (saved && typeof saved.image === 'string' && /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(saved.image)) settings.image = saved.image;
 if (saved && Number.isFinite(saved.shade)) settings.shade = Math.max(30, Math.min(95, saved.shade));
} catch (_) {}
function apply() {
 document.documentElement.style.setProperty('--wallpaper', settings.image ? 'url("' + settings.image + '")' : 'none');
 document.documentElement.style.setProperty('--shade', settings.shade / 100);
 shade.value = settings.shade;
}
function save() {
 apply();
 try { localStorage.setItem(key, JSON.stringify(settings)); message.textContent = 'Fond enregistré dans ce navigateur.'; }
 catch (_) { message.textContent = 'Stockage indisponible ou plein : le fond est temporaire. Essayez une image plus petite.'; }
}
function fitWallpaper(preview) {
 const canvas = document.createElement('canvas');
 const scale = Math.min(1, 1920 / preview.naturalWidth, 1080 / preview.naturalHeight);
 canvas.width = Math.max(1, Math.round(preview.naturalWidth * scale));
 canvas.height = Math.max(1, Math.round(preview.naturalHeight * scale));
 const context = canvas.getContext('2d');
 if (!context) throw new Error('canvas unavailable');
 context.fillStyle = '#101827'; context.fillRect(0, 0, canvas.width, canvas.height);
 context.drawImage(preview, 0, 0, canvas.width, canvas.height);
 for (const quality of [.85, .7, .5]) {
  const encoded = canvas.toDataURL('image/jpeg', quality);
  if (encoded.startsWith('data:image/jpeg;base64,') && encoded.length <= maxDataLength) return encoded;
 }
 throw new Error('image too large');
}
image.addEventListener('change', () => {
 const file = image.files[0]; if (!file) return;
 if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
  message.textContent = 'Choisissez une image JPG, PNG ou WebP de 2 Mo maximum.'; image.value = ''; return;
 }
 const reader = new FileReader();
 reader.onerror = () => { message.textContent = 'Impossible de lire cette image.'; };
 reader.onload = () => {
  const preview = new Image();
  preview.onload = () => {
   try { settings.image = fitWallpaper(preview); save(); }
   catch (_) { message.textContent = 'Impossible de préparer cette image. Essayez une image plus petite.'; }
  };
  preview.onerror = () => { message.textContent = 'Le fichier ne contient pas une image lisible.'; };
  preview.src = reader.result;
 };
 reader.readAsDataURL(file);
});
shade.addEventListener('input', () => { settings.shade = Number(shade.value); save(); });
document.getElementById('wallpaper-reset').addEventListener('click', () => {
 settings = {image: '', shade: 75}; image.value = ''; save();
});
apply();
if (settings.image.length > maxDataLength) {
 const previous = new Image();
 previous.onload = () => {
  try { settings.image = fitWallpaper(previous); save(); }
  catch (_) { message.textContent = 'Le fond enregistré est trop grand : choisissez une image plus petite.'; }
 };
 previous.src = settings.image;
}
if (document.body.dataset.refresh === '30') {
 setInterval(() => {
  if (!document.hidden && !document.querySelector('.wallpaper-settings[open]')) window.location.reload();
 }, 30000);
}
})();"""
SCRIPT_HASH = base64.b64encode(sha256(SCRIPT.encode()).digest()).decode()
STYLE = """<style>
:root{--wallpaper:none;--shade:.75;background:#101827}
body{background:transparent!important;isolation:isolate}
body{box-sizing:border-box;padding:clamp(1rem,4vw,2rem)!important}
body>p,body>h1,body>ol,body>ul,body>form,body>details,body>nav{background:rgba(16,24,39,.94);border-radius:8px;padding:1rem}
body>ol{padding-left:4.5rem}
p,a,code,pre,li{overflow-wrap:anywhere}input,textarea{max-width:100%;box-sizing:border-box}textarea{width:100%}
main{grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))}
button{min-height:44px}a{display:inline-block;max-width:100%;min-height:44px;align-content:center}
body::before{content:'';position:fixed;inset:0;z-index:-1;pointer-events:none;background-image:linear-gradient(rgba(16,24,39,var(--shade)),rgba(16,24,39,var(--shade))),var(--wallpaper);background-size:cover;background-position:center}
.wallpaper-settings{margin:1.5rem 0;padding:1rem;background:#1d2b3e;border:1px solid #3b5369;border-radius:12px;color:#eef3fa}
/* Resource cards remain together when the window becomes a small monitor. */
.dashboard-grid>section{min-width:0}
.dashboard .resource-card .donut{width:clamp(96px,24vw,190px);height:auto;aspect-ratio:1}
.dashboard .resource-card .donut-center{width:78%;height:78%}
@media(max-width:640px),(max-height:540px){
 body.dashboard{padding:.5rem!important;font-size:13px}
 .dashboard>h1{font-size:1.1rem;margin:0 0 .35rem;padding:.4rem .6rem}
 .dashboard>.dashboard-nav{margin:0 0 .5rem;padding:0 .5rem;font-size:12px}
 .dashboard-nav a{min-height:32px}
 .dashboard>.dashboard-measurement{display:none}
 .dashboard main.dashboard-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}
 .dashboard-grid>section{padding:.5rem;border-radius:8px}
 .dashboard-grid h2{font-size:clamp(.8rem,2.5vw,1rem);margin:0 0 .35rem}
 .dashboard .resource-card .donut{width:clamp(88px,23vw,128px);margin:.4rem auto}
 .dashboard .donut-center b{font-size:clamp(1rem,3vw,1.4rem)}
 .dashboard .donut-center span,.dashboard .donut-center small{font-size:11px}
 .dashboard .donut-center{gap:.1rem}
 .dashboard .capacity{font-size:12px;line-height:1.35;margin:.4rem 0 0}
 .dashboard-grid>section:not(.resource-card){grid-column:1/-1}
 .dashboard>.wallpaper-settings{margin:.5rem 0;padding:.5rem}
}
/* Tiny windows (not phones held upright) are a text-only resource monitor; enlarge to restore controls. */
@media(max-height:260px),(max-width:360px) and (max-height:540px){
 body.dashboard{font-size:13px;padding:.4rem!important}
 body.dashboard::before{background:#101827;background-image:none}
 .dashboard>:not(main){display:none}
 .dashboard main.dashboard-grid{grid-template-columns:14px minmax(0,1fr);column-gap:.35rem;row-gap:0}
 .dashboard .reference-status{display:block;width:10px;height:10px;min-width:10px;max-width:10px;min-height:10px;max-height:10px;padding:0;box-sizing:border-box;border-radius:50%;grid-column:1;grid-row:1/span 2;align-self:center;justify-self:center}
 .dashboard .reference-status:focus-visible{outline:2px solid #eef3fa;outline-offset:3px}
 .dashboard .resource-card{grid-column:2}
 .dashboard-grid>section:not(.resource-card){display:none}
 .dashboard .resource-card{padding:0;border:0;background:transparent}
 .dashboard .resource-card>:not(.resource-text){display:none}
 .dashboard .resource-card .resource-text{display:block;margin:.25rem 0;line-height:1.4;overflow-wrap:anywhere}
}
.wallpaper-settings summary{cursor:pointer}.wallpaper-settings label{display:block;margin:1rem 0}.wallpaper-settings input{max-width:100%}.wallpaper-settings button{padding:.6rem;cursor:pointer}.wallpaper-settings p{line-height:1.5}
</style>"""
CONTROLS = """<details class="wallpaper-settings"><summary>Personnaliser le fond d’écran</summary>
<p>Choisissez votre image JPG, PNG ou WebP (2 Mo maximum). Elle reste dans ce navigateur et n’est pas envoyée au serveur.</p>
<p>Une copie adaptée à l’écran est préparée localement. Le rafraîchissement est suspendu pendant ce réglage.</p>
<label>Image de fond <input id="wallpaper-file" type="file" accept="image/jpeg,image/png,image/webp"></label>
<label>Assombrissement <input id="wallpaper-shade" type="range" min="30" max="95" value="75"></label>
<button id="wallpaper-reset" type="button">Rétablir le fond par défaut</button>
<p id="wallpaper-message" role="status" aria-live="polite"></p></details>"""


def decorate(page):
    return page.replace('</head>', STYLE + '</head>', 1).replace(
        '</body>', CONTROLS + '<script>' + SCRIPT + '</script></body>', 1)
