(function initQuestionCards() {
    document.querySelectorAll('.question-card').forEach(card => {
        const buttons = card.querySelectorAll('button[data-answer]');
        const followup = card.querySelector('.question-followup');

        buttons.forEach(button => {
            button.addEventListener('click', () => {
                buttons.forEach(btn => btn.classList.remove('selected'));
                button.classList.add('selected');

                if (followup) {
                    if (button.dataset.answer === 'no') {
                        followup.classList.add('visible');
                    } else {
                        followup.classList.remove('visible');
                    }
                }
            });
        });
    });
})();
