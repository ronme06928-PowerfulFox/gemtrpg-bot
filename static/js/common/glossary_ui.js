(function () {
    const state = {
        initialized: false,
        eventsBound: false,
        dataLoaded: false,
        dataPromise: null,
        terms: {},
        tooltipEl: null,
        popupBackdropEl: null,
    };

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function _isTouchLike() {
        return ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
    }

    function _ensureTooltipEl() {
        if (state.tooltipEl) return state.tooltipEl;
        const el = document.createElement('div');
        el.className = 'glossary-tooltip';
        el.setAttribute('role', 'tooltip');
        el.style.display = 'none';
        document.body.appendChild(el);
        state.tooltipEl = el;
        return el;
    }

    function _ensurePopupEl() {
        if (state.popupBackdropEl) return state.popupBackdropEl;

        const backdrop = document.createElement('div');
        backdrop.className = 'glossary-popup-backdrop';
        backdrop.setAttribute('aria-hidden', 'true');
        backdrop.innerHTML = '' +
            '<div class="glossary-popup" role="dialog" aria-modal="true" aria-label="用語説明">' +
            '  <button type="button" class="glossary-popup-close" aria-label="閉じる">×</button>' +
            '  <div class="glossary-popup-title"></div>' +
            '  <div class="glossary-popup-category"></div>' +
            '  <div class="glossary-popup-short"></div>' +
            '  <div class="glossary-popup-long"></div>' +
            '  <div class="glossary-popup-flavor"></div>' +
            '  <div class="glossary-popup-links"></div>' +
            '</div>';

        backdrop.addEventListener('click', (e) => {
            if (e.target === backdrop) hideAll();
        });

        const closeBtn = backdrop.querySelector('.glossary-popup-close');
        if (closeBtn) closeBtn.addEventListener('click', hideAll);

        document.body.appendChild(backdrop);
        state.popupBackdropEl = backdrop;
        return backdrop;
    }

    function _positionTooltip(anchorEl, tooltipEl) {
        const rect = anchorEl.getBoundingClientRect();
        const margin = 8;
        const maxWidth = Math.min(360, window.innerWidth - margin * 2);
        tooltipEl.style.maxWidth = `${maxWidth}px`;
        tooltipEl.style.display = 'block';

        const ttRect = tooltipEl.getBoundingClientRect();
        let left = rect.left;
        if (left + ttRect.width > window.innerWidth - margin) {
            left = window.innerWidth - margin - ttRect.width;
        }
        if (left < margin) left = margin;

        let top = rect.bottom + 6;
        if (top + ttRect.height > window.innerHeight - margin) {
            top = rect.top - ttRect.height - 6;
        }
        if (top < margin) top = margin;

        tooltipEl.style.left = `${Math.round(left)}px`;
        tooltipEl.style.top = `${Math.round(top)}px`;
    }

    function ensureDataLoaded() {
        if (state.dataLoaded) return Promise.resolve(state.terms);
        if (state.dataPromise) return state.dataPromise;

        if (window.glossaryData && typeof window.glossaryData === 'object') {
            state.terms = window.glossaryData;
            state.dataLoaded = true;
            return Promise.resolve(state.terms);
        }

        state.dataPromise = fetch('/api/get_glossary_data')
            .then((res) => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data) => {
                state.terms = (data && typeof data === 'object') ? data : {};
                window.glossaryData = state.terms;
                state.dataLoaded = true;
                return state.terms;
            })
            .catch((err) => {
                console.warn('[Glossary] data load failed:', err);
                state.terms = {};
                state.dataLoaded = true;
                return state.terms;
            })
            .finally(() => {
                state.dataPromise = null;
            });

        return state.dataPromise;
    }

    function getTerm(termId) {
        if (!termId) return null;
        return state.terms[String(termId).trim()] || null;
    }

    function parseMarkupToHTML(text) {
        const src = String(text ?? '');
        const regex = /\[\[([^|\]]+?)(?:\|([^\]]+?))?\]\]/g;

        let html = '';
        let lastIndex = 0;
        let match = null;

        while ((match = regex.exec(src)) !== null) {
            html += escapeHtml(src.slice(lastIndex, match.index));

            const termId = String(match[1] || '').trim();
            const explicitLabel = String(match[2] || '').trim();
            const term = getTerm(termId);
            const label = explicitLabel || (term && term.display_name) || termId || '???';
            const known = term ? '1' : '0';

            html += `<span class="glossary-term${known === '1' ? '' : ' is-missing'}" data-term-id="${escapeHtml(termId)}" data-term-known="${known}" tabindex="0" role="button">${escapeHtml(label)}</span>`;
            lastIndex = regex.lastIndex;
        }

        html += escapeHtml(src.slice(lastIndex));
        return html.replace(/\n/g, '<br>');
    }

    function _relatedLabel(termId) {
        const term = getTerm(termId);
        return term ? term.display_name || termId : termId;
    }

    function _renderPopup(termId) {
        const backdrop = _ensurePopupEl();
        const popup = backdrop.querySelector('.glossary-popup');
        if (!popup) return;

        const term = getTerm(termId);
        const title = popup.querySelector('.glossary-popup-title');
        const category = popup.querySelector('.glossary-popup-category');
        const shortEl = popup.querySelector('.glossary-popup-short');
        const longEl = popup.querySelector('.glossary-popup-long');
        const flavorEl = popup.querySelector('.glossary-popup-flavor');
        const linksEl = popup.querySelector('.glossary-popup-links');

        const fallbackTitle = termId || '用語';
        if (title) title.textContent = term ? (term.display_name || fallbackTitle) : fallbackTitle;
        if (category) category.textContent = term && term.category ? `分類: ${term.category}` : '';

        const shortText = term ? (term.short || '') : '';
        const longText = term ? (term.long || '') : '';
        const flavorText = term ? (term.flavor || '') : '';
        const mainText = longText || shortText || '説明未登録';

        if (shortEl) {
            shortEl.textContent = shortText && longText ? shortText : '';
        }
        if (longEl) {
            longEl.textContent = mainText;
        }
        if (flavorEl) {
            flavorEl.textContent = flavorText || '';
            flavorEl.style.display = flavorText ? 'block' : 'none';
        }

        if (linksEl) {
            const links = (term && Array.isArray(term.links)) ? term.links.filter(Boolean) : [];
            if (links.length) {
                linksEl.textContent = '';
                const prefix = document.createElement('span');
                prefix.textContent = '関連: ';
                linksEl.appendChild(prefix);

                links.forEach((linkId, index) => {
                    const linkBtn = document.createElement('button');
                    linkBtn.type = 'button';
                    linkBtn.className = 'glossary-popup-link';
                    linkBtn.setAttribute('data-term-id', String(linkId));
                    linkBtn.textContent = _relatedLabel(linkId);
                    linksEl.appendChild(linkBtn);

                    if (index < links.length - 1) {
                        const sep = document.createElement('span');
                        sep.className = 'glossary-popup-sep';
                        sep.textContent = ' / ';
                        linksEl.appendChild(sep);
                    }
                });
                linksEl.style.display = 'block';
            } else {
                linksEl.textContent = '';
                linksEl.style.display = 'none';
            }
        }

        backdrop.classList.add('is-open');
        backdrop.setAttribute('aria-hidden', 'false');
    }

    function showTooltip(anchorEl) {
        if (_isTouchLike()) return;
        if (!anchorEl) return;

        const termId = anchorEl.getAttribute('data-term-id');
        if (!termId) return;

        const term = getTerm(termId);
        if (!term || !term.short) {
            hideTooltip();
            return;
        }

        const tooltip = _ensureTooltipEl();
        tooltip.textContent = term.short;
        _positionTooltip(anchorEl, tooltip);
    }

    function hideTooltip() {
        if (!state.tooltipEl) return;
        state.tooltipEl.style.display = 'none';
    }

    function showPopup(termOrEl) {
        const termId = (typeof termOrEl === 'string')
            ? termOrEl
            : (termOrEl && termOrEl.getAttribute && termOrEl.getAttribute('data-term-id'));
        if (!termId) return;
        _renderPopup(termId);
    }

    function hideAll() {
        hideTooltip();
        if (state.popupBackdropEl) {
            state.popupBackdropEl.classList.remove('is-open');
            state.popupBackdropEl.setAttribute('aria-hidden', 'true');
        }
    }

    function _onPointerEnter(e) {
        const termEl = e.target && e.target.closest ? e.target.closest('.glossary-term') : null;
        if (!termEl) return;
        showTooltip(termEl);
    }

    function _onPointerLeave(e) {
        const termEl = e.target && e.target.closest ? e.target.closest('.glossary-term') : null;
        if (!termEl) return;
        const toEl = e.relatedTarget;
        if (toEl && termEl.contains(toEl)) return;
        hideTooltip();
    }

    function _onClick(e) {
        const relatedLinkEl = e.target && e.target.closest ? e.target.closest('.glossary-popup-link') : null;
        if (relatedLinkEl) {
            e.preventDefault();
            hideTooltip();
            showPopup(relatedLinkEl);
            return;
        }

        const termEl = e.target && e.target.closest ? e.target.closest('.glossary-term') : null;
        if (!termEl) return;
        e.preventDefault();
        hideTooltip();
        showPopup(termEl);
    }

    function _onKeyDown(e) {
        if (e.key === 'Escape') {
            hideAll();
            return;
        }
        const active = document.activeElement;
        if (!active || !active.classList || !active.classList.contains('glossary-term')) return;
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            showPopup(active);
        }
    }

    function bindDelegatedEvents() {
        if (state.eventsBound) return;
        state.eventsBound = true;
        document.addEventListener('mouseover', _onPointerEnter);
        document.addEventListener('mouseout', _onPointerLeave);
        document.addEventListener('click', _onClick);
        document.addEventListener('keydown', _onKeyDown);
    }

    function initOnce() {
        if (state.initialized) return;
        state.initialized = true;
        bindDelegatedEvents();
        ensureDataLoaded();
    }

    window.Glossary = {
        initOnce,
        ensureDataLoaded,
        getTerm,
        parseMarkupToHTML,
        bindDelegatedEvents,
        showTooltip,
        showPopup,
        hideAll,
        escapeHtml,
    };
})();
