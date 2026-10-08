const prefectoDialog = document.getElementById('prefecto-dialog');

if (prefectoDialog) {
    document.querySelectorAll('[data-open-prefecto]').forEach(button => {
        button.addEventListener('click', () => prefectoDialog.showModal());
    });
    prefectoDialog.querySelectorAll('[data-close-prefecto]').forEach(button => {
        button.addEventListener('click', () => prefectoDialog.close());
    });
    prefectoDialog.addEventListener('click', event => {
        if (event.target === prefectoDialog) prefectoDialog.close();
    });
    if (prefectoDialog.dataset.openOnError === 'true') prefectoDialog.showModal();
}

const manualPassword = document.getElementById('id_contrasena_manual');
const passwordModes = document.querySelectorAll('input[name="metodo_contrasena"]');
if (manualPassword && passwordModes.length) {
    const syncPasswordMode = () => {
        const manual = document.querySelector('input[name="metodo_contrasena"]:checked')?.value === 'manual';
        manualPassword.closest('.gestion-field').hidden = !manual;
        manualPassword.disabled = !manual;
        manualPassword.required = manual;
        if (!manual) manualPassword.value = '';
    };
    passwordModes.forEach(mode => mode.addEventListener('change', syncPasswordMode));
    syncPasswordMode();
}
