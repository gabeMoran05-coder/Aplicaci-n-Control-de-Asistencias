const tabs = [...document.querySelectorAll('.tab')];
const popover = document.getElementById('day-popover');
const editor = document.getElementById('calendar-editor');
const eventForm = document.getElementById('event-form');
const cancelForm = document.querySelector('#cancel-editor form');
const editorTitle = document.getElementById('editor-title');
const newEventButton = document.getElementById('event-new');
let pinned = false;
let closeTimer;
let selectedDate = '';

function selectTab(name) {
    tabs.forEach((tab) => {
        const active = tab.dataset.tab === name;
        tab.setAttribute('aria-selected', String(active));
        document.getElementById(tab.dataset.tab).hidden = !active;
    });
    sessionStorage.setItem('asiste-calendar-tab', name);
}

tabs.forEach((tab) => tab.addEventListener('click', () => selectTab(tab.dataset.tab)));
const savedTab = sessionStorage.getItem('asiste-calendar-tab');
if (savedTab && document.getElementById(savedTab)?.classList.contains('tab-panel')) {
    selectTab(savedTab);
}

function hidePopover() {
    if (!pinned) popover.hidden = true;
}

function closePopover() {
    pinned = false;
    clearTimeout(closeTimer);
    popover.hidden = true;
}

function showPopover(button, pin) {
    if (editor.open) return;
    clearTimeout(closeTimer);
    pinned = pin;
    selectedDate = button.dataset.date;
    popover.querySelector('h3').textContent = button.dataset.label;
    popover.querySelector('.popover-body').replaceChildren(button.nextElementSibling.content.cloneNode(true));
    document.getElementById('quick-cancel').hidden = !!button.dataset.closed;
    document.getElementById('quick-event').hidden = !!button.closest('.out-cycle');
    popover.hidden = false;
    const rect = button.getBoundingClientRect();
    popover.style.left = Math.max(12, Math.min(rect.left, innerWidth - popover.offsetWidth - 12)) + 'px';
    popover.style.top = Math.max(12, Math.min(rect.bottom + 6, innerHeight - popover.offsetHeight - 12)) + 'px';
}

document.querySelectorAll('.day-button').forEach((button) => {
    button.addEventListener('mouseenter', () => showPopover(button, false));
    button.addEventListener('focus', () => showPopover(button, false));
    button.addEventListener('click', () => showPopover(button, true));
    button.closest('.day').addEventListener('mouseleave', () => {
        closeTimer = setTimeout(hidePopover, 250);
    });
});
popover.addEventListener('mouseenter', () => clearTimeout(closeTimer));
popover.addEventListener('mouseleave', () => { pinned = false; hidePopover(); });
popover.querySelector('.close').addEventListener('click', closePopover);
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closePopover();
});
document.addEventListener('click', (event) => {
    if (!popover.contains(event.target) && !event.target.closest('.day-button')) closePopover();
});

function openEditor(kind, date, eventData = null) {
    closePopover();
    selectedDate = date;
    const isEvent = kind === 'eventos';
    selectTab(kind === 'eventos' ? 'eventos' : 'cancelaciones');
    document.getElementById('cancel-editor').hidden = isEvent;
    document.getElementById('event-editor').hidden = !isEvent;
    if (isEvent) {
        eventForm.reset();
        eventForm.elements.fecha.value = date;
        eventForm.elements.evento_id.value = eventData?.id || '';
        eventForm.elements.titulo.value = eventData?.title || '';
        eventForm.elements.detalle.value = eventData?.detail || '';
        editorTitle.textContent = eventData ? 'Editar evento' : 'Agregar evento';
        newEventButton.hidden = !eventData;
    } else {
        cancelForm.reset();
        cancelForm.elements.fecha.value = date;
        editorTitle.textContent = 'Cancelar clases';
    }
    if (!editor.open) editor.showModal();
    (isEvent && eventData ? eventForm.elements.titulo : isEvent ? eventForm.elements.fecha : cancelForm.elements.motivo).focus();
}

document.getElementById('quick-cancel').addEventListener('click', () => openEditor('cancelaciones', selectedDate));
document.getElementById('quick-event').addEventListener('click', () => openEditor('eventos', selectedDate));
document.querySelectorAll('.edit-event').forEach((button) => {
    button.addEventListener('click', () => openEditor('eventos', button.dataset.date, {
        id: button.dataset.id,
        title: button.dataset.title,
        detail: button.dataset.detail,
    }));
});
newEventButton.addEventListener('click', () => openEditor('eventos', selectedDate));
editor.querySelector('.editor-close').addEventListener('click', () => editor.close());
editor.querySelectorAll('.editor-dismiss').forEach((button) => button.addEventListener('click', () => editor.close()));
editor.addEventListener('click', (event) => {
    if (event.target === editor) editor.close();
});
