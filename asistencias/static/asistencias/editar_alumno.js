const preview = document.getElementById('photo-preview');
const placeholder = document.getElementById('photo-placeholder');
const inputs = [document.getElementById('camera-input'), document.getElementById('file-input')];
let objectUrl;
inputs.forEach(input => input.addEventListener('change', () => {
    const file = input.files[0];
    if (!file) return;
    inputs.filter(other => other !== input).forEach(other => { other.value = ''; });
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    preview.src = objectUrl;
    preview.hidden = false;
    if (placeholder) placeholder.hidden = true;
}));
window.addEventListener('pagehide', () => { if (objectUrl) URL.revokeObjectURL(objectUrl); });
