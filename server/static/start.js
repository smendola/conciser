(function initStartPage() {
    const isEdge = navigator.userAgent.indexOf('Edg') !== -1;
    const browserName = isEdge ? 'Edge' : 'Chrome';
    const extensionsURL = isEdge ? 'edge://extensions/' : 'chrome://extensions/';

    document.querySelectorAll('#browser-name, #browser-name-install').forEach(el => {
        el.textContent = browserName;
    });

    const urlElement = document.getElementById('extensions-url');
    if (urlElement) {
        urlElement.textContent = extensionsURL;
    }

    window.copyExtensionsURL = function copyExtensionsURL() {
        const feedback = document.getElementById('copy-feedback');
        const btn = document.getElementById('copy-url-btn');

        function showCopiedState() {
            if (!feedback || !btn) return;

            feedback.style.display = 'block';
            btn.classList.add('copied');
            btn.innerHTML = '✅ Copied to Clipboard!';

            setTimeout(() => {
                feedback.style.display = 'none';
                btn.classList.remove('copied');
                btn.innerHTML = '📋 Click to Copy: <code id="extensions-url" style="background: transparent; color: white;">' + extensionsURL + '</code>';
            }, 3000);
        }

        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            navigator.clipboard.writeText(extensionsURL)
                .then(showCopiedState)
                .catch(fallbackCopy);
            return;
        }

        fallbackCopy();

        function fallbackCopy() {
            const textArea = document.createElement('textarea');
            textArea.value = extensionsURL;
            textArea.setAttribute('readonly', '');
            textArea.style.position = 'fixed';
            textArea.style.left = '-9999px';
            document.body.appendChild(textArea);
            textArea.select();

            try {
                const copied = document.execCommand('copy');
                if (copied) {
                    showCopiedState();
                } else {
                    alert('Copy failed. Please manually copy this URL:\n\n' + extensionsURL);
                }
            } catch (err) {
                alert('Copy failed. Please manually copy this URL:\n\n' + extensionsURL);
            } finally {
                document.body.removeChild(textArea);
            }
        }
    };
})();
