document.querySelectorAll('.compact-calendar').forEach(calendar => {
    const detail = calendar.querySelector('.selected-day');
    const buttons = [...calendar.querySelectorAll('.date-button')];
    const select = button => {
        buttons.forEach(item => item.setAttribute('aria-pressed', item === button ? 'true' : 'false'));
        const template = calendar.querySelector('#' + button.dataset.detail);
        detail.replaceChildren(template.content.cloneNode(true));
    };
    buttons.forEach(button => button.addEventListener('click', () => select(button)));
    const initial = buttons.find(button => button.classList.contains('is-today')) || buttons[0];
    if (initial) select(initial);
});
