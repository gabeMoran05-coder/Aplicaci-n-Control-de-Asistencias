const table = document.getElementById('student-table');
if (table) {
    const headers = [...table.querySelectorAll('th button[data-sort]')];
    const collator = new Intl.Collator('es', {numeric: true, sensitivity: 'base'});
    let current = 0;
    let direction = 1;
    headers.forEach(button => button.addEventListener('click', () => {
        const column = Number(button.dataset.sort);
        direction = column === current ? -direction : 1;
        current = column;
        const rows = [...table.tBodies[0].rows].filter(row => row.cells.length === 7);
        rows.sort((a, b) => {
            const left = a.cells[column].dataset.value || '';
            const right = b.cells[column].dataset.value || '';
            if (!left) return right ? 1 : 0;
            if (!right) return -1;
            return collator.compare(left, right) * direction;
        });
        rows.forEach(row => table.tBodies[0].append(row));
        headers.forEach(item => {
            const th = item.closest('th');
            th.removeAttribute('aria-sort');
            item.querySelector('.sort-arrow').textContent = '↕';
        });
        button.closest('th').setAttribute('aria-sort', direction === 1 ? 'ascending' : 'descending');
        button.querySelector('.sort-arrow').textContent = direction === 1 ? '↑' : '↓';
    }));
    document.querySelectorAll('.filters select').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));
}
