'use strict';
const $ = id => document.getElementById(id);
function showTab(name) {
  document.querySelectorAll('.tab').forEach(button => {
    const active = button.dataset.tab === name;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  ['analytics','evidence','spatial'].forEach(tab => $(tab+'-panel').hidden = tab !== name);
}
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => showTab(button.dataset.tab)));
$('filters').addEventListener('submit', event => event.preventDefault());
$('status').textContent = 'StreetTwin workspace ready. Archive connection is the next slice.';
