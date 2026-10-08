document.querySelectorAll('[data-phone-country]').forEach(country => {
    const input = document.getElementById(country.dataset.phoneTarget);
    if (!input) return;

    const updatePlaceholder = () => {
        input.placeholder = country.value === 'MX' ? '314-181-0105' :
            country.value === 'US' || country.value === 'CA' ? '202-555-0123' : 'Número nacional';
    };
    const format = () => {
        const oldValue = input.value;
        const cursor = input.selectionStart;
        const digitsBeforeCursor = oldValue.slice(0, cursor).replace(/\D/g, '').length;
        let value = oldValue.replace(/[^+0-9().\s-]/g, '');
        if (country.value === 'MX' && !value.startsWith('+')) {
            const digits = value.replace(/\D/g, '').slice(0, 10);
            value = [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6)].filter(Boolean).join('-');
        }
        if (value !== oldValue) {
            input.value = value;
            if (document.activeElement === input) {
                let position = 0;
                let count = 0;
                while (position < value.length && count < digitsBeforeCursor) {
                    if (/\d/.test(value[position])) count++;
                    position++;
                }
                input.setSelectionRange(position, position);
            }
        }
    };
    updatePlaceholder();
    input.addEventListener('input', format);
    country.addEventListener('change', () => {
        updatePlaceholder();
        format();
    });
});
