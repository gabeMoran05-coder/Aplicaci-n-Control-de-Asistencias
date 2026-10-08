const preview = document.getElementById('photo-preview');
const placeholder = document.getElementById('photo-placeholder');
const inputs = [document.getElementById('camera-input'), document.getElementById('file-input')];
const selectedPhoto = document.getElementById('selected-photo');
const removePhoto = document.querySelector('.remove-photo input');
document.querySelectorAll('.photo-buttons label').forEach(label => {
    label.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            document.getElementById(label.htmlFor).click();
        }
    });
});
let objectUrl;
inputs.forEach(input => input.addEventListener('change', () => {
    const file = input.files[0];
    if (!file) return;
    inputs.filter(other => other !== input).forEach(other => { other.value = ''; });
    if (removePhoto) removePhoto.checked = false;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    preview.src = objectUrl;
    preview.hidden = false;
    if (placeholder) placeholder.hidden = true;
    selectedPhoto.textContent = file.name;
}));
window.addEventListener('pagehide', () => { if (objectUrl) URL.revokeObjectURL(objectUrl); });
