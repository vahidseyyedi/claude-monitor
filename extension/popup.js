const labelInput = document.getElementById('label');
const statusEl = document.getElementById('status');

chrome.storage.local.get(['accountLabel'], (res) => {
  if (res.accountLabel) labelInput.value = res.accountLabel;
});

document.getElementById('save').addEventListener('click', () => {
  const label = labelInput.value.trim();
  if (!label) return;
  chrome.storage.local.set({ accountLabel: label }, () => {
    statusEl.textContent = 'ذخیره شد: ' + label;
  });
});
