document.querySelectorAll('[data-copy-markdown]').forEach(button => {
  button.addEventListener('click', async () => {
    const status = button.parentElement.querySelector('[role="status"]');
    button.disabled = true;
    try {
      const response = await fetch(button.dataset.copyMarkdown);
      if (!response.ok) throw new Error('Markdown unavailable');
      const text = await response.text();
      if (!text.startsWith('# ')) throw new Error('Export not built');
      await navigator.clipboard.writeText(text);
      status.textContent = 'Copied.';
    } catch (_) { status.textContent = 'Use Read Markdown to open and copy the article.'; }
    finally { button.disabled = false; }
  });
});
