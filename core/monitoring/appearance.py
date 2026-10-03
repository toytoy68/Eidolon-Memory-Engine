"""Browser-local wallpaper preferences, independent of canonical memory."""
import base64
from hashlib import sha256

SCRIPT = r"""(() => {
const key = 'eidolon-wallpaper-v1';
const image = document.getElementById('wallpaper-file');
const shade = document.getElementById('wallpaper-shade');
const message = document.getElementById('wallpaper-message');
let settings = {image: '', shade: 75};
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
image.addEventListener('change', () => {
 const file = image.files[0]; if (!file) return;
 if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
  message.textContent = 'Choisissez une image JPG, PNG ou WebP de 2 Mo maximum.'; image.value = ''; return;
 }
 const reader = new FileReader();
 reader.onerror = () => { message.textContent = 'Impossible de lire cette image.'; };
 reader.onload = () => {
  const preview = new Image();
  preview.onload = () => { settings.image = reader.result; save(); };
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
})();"""
SCRIPT_HASH = base64.b64encode(sha256(SCRIPT.encode()).digest()).decode()
STYLE = """<style>
:root{--wallpaper:none;--shade:.75;background:#101827}
body{background:transparent!important;isolation:isolate}
body::before{content:'';position:fixed;inset:0;z-index:-1;pointer-events:none;background-image:linear-gradient(rgba(16,24,39,var(--shade)),rgba(16,24,39,var(--shade))),var(--wallpaper);background-size:cover;background-position:center}
.wallpaper-settings{margin:1.5rem 0;padding:1rem;background:#1d2b3e;border:1px solid #3b5369;border-radius:12px;color:#eef3fa}
.wallpaper-settings summary{cursor:pointer}.wallpaper-settings label{display:block;margin:1rem 0}.wallpaper-settings input{max-width:100%}.wallpaper-settings button{padding:.6rem;cursor:pointer}.wallpaper-settings p{line-height:1.5}
</style>"""
CONTROLS = """<details class="wallpaper-settings"><summary>Personnaliser le fond d’écran</summary>
<p>Choisissez votre image JPG, PNG ou WebP (2 Mo maximum). Elle reste dans ce navigateur et n’est pas envoyée au serveur.</p>
<label>Image de fond <input id="wallpaper-file" type="file" accept="image/jpeg,image/png,image/webp"></label>
<label>Assombrissement <input id="wallpaper-shade" type="range" min="30" max="95" value="75"></label>
<button id="wallpaper-reset" type="button">Rétablir le fond par défaut</button>
<p id="wallpaper-message" role="status" aria-live="polite"></p></details>"""


def decorate(page):
    return page.replace('</head>', STYLE + '</head>', 1).replace(
        '</body>', CONTROLS + '<script>' + SCRIPT + '</script></body>', 1)
