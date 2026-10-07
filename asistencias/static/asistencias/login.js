document.querySelectorAll('.password-toggle').forEach((button) => {
    const field = button.closest('.password-field');
    const input = field.querySelector('input');
    button.addEventListener('click', () => {
        const visible = input.type === 'password';
        input.type = visible ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(visible));
        button.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
        button.title = visible ? 'Ocultar contraseña' : 'Mostrar contraseña';
    });
});
