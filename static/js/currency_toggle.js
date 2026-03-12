var CurrencyToggle = (function () {
    var SYMBOLS = {
        'USD':'$','EUR':'€','GBP':'£',
        'BRL':'R$','ZAR':'R','MYR':'RM',
        'ARS':'AR$','CLP':'CL$','COP':'COL$','PEN':'S/','MXN':'MX$',
        'CAD':'C$','AUD':'A$','NZD':'NZ$','SGD':'S$','HKD':'HK$',
        'TWD':'NT$','CHF':'CHF','IDR':'Rp','KES':'KSh','EGP':'E£',
        'MMK':'K','SEK':'kr','NOK':'kr','DKK':'kr','ISK':'kr',
        'HUF':'Ft','CZK':'Kč','RON':'lei','HRK':'kn','RSD':'din',
        // Multi-byte/RTL problematic symbols: Use currency codes only
        'JPY':'JPY','CNY':'CNY','INR':'INR','KRW':'KRW','THB':'THB',
        'RUB':'RUB','TRY':'TRY','PLN':'PLN','PHP':'PHP','VND':'VND',
        'ILS':'ILS','NGN':'NGN','UAH':'UAH','GHS':'GHS','PKR':'PKR',
        'LKR':'LKR','NPR':'NPR','BDT':'BDT','LAK':'LAK','KHR':'KHR',
        'MNT':'MNT','CRC':'CRC','PYG':'PYG','AED':'AED','SAR':'SAR',
        'QAR':'QAR','KWD':'KWD','BHD':'BD','OMR':'OMR','JOD':'JOD',
        'BGN':'BGN'
    };

    var fxRates = null;
    var fxBase = null;
    var fxTimestamp = null;
    var fxTimestampDisplay = '';
    var fetchingRates = false;

    function sym(code) {
        return SYMBOLS[code] || code;
    }

    function formatAmount(val, code) {
        var s = sym(code);
        if (val < 0) return '-' + s + Math.abs(val).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
        return s + val.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
    }

    function formatMultiRaw(balances) {
        var codes = Object.keys(balances).sort();
        var parts = [];
        for (var i = 0; i < codes.length; i++) {
            var code = codes[i];
            var val = parseFloat(balances[code]);
            if (Math.abs(val) < 0.005) continue;
            var s = sym(code);
            if (val > 0) parts.push('+' + s + val.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}));
            else parts.push('-' + s + Math.abs(val).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}));
        }
        if (parts.length === 0) return '$0.00';
        var result = parts[0];
        for (var j = 1; j < parts.length; j++) {
            if (parts[j].charAt(0) === '-') result += ' - ' + parts[j].substring(1);
            else result += ' + ' + parts[j].substring(1);
        }
        return result;
    }

    function convertAmount(amount, fromCurr, toCurr, rates) {
        if (fromCurr === toCurr) return amount;
        var fromRate = rates[fromCurr] || 1;
        var toRate = rates[toCurr] || 1;
        if (fromRate === 0) return amount;
        return amount / fromRate * toRate;
    }

    function computeUnified(balances, targetCurrency, rates) {
        var total = 0;
        for (var code in balances) {
            if (!balances.hasOwnProperty(code)) continue;
            total += convertAmount(parseFloat(balances[code]), code, targetCurrency, rates);
        }
        return Math.round(total * 100) / 100;
    }

    function detectSign(balances, rates) {
        // For multi-currency balances, convert to INR to determine color
        var total = 0;
        for (var code in balances) {
            if (!balances.hasOwnProperty(code)) continue;
            total += convertAmount(parseFloat(balances[code]), code, 'INR', rates);
        }
        if (total > 0.005) return 1;
        if (total < -0.005) return -1;
        return 0;
    }

    function applyColor(el, sign) {
        el.classList.remove('balance-positive', 'balance-negative', 'balance-neutral');
        if (sign > 0) el.classList.add('balance-positive');
        else if (sign < 0) el.classList.add('balance-negative');
        else el.classList.add('balance-neutral');
    }

    function fetchRates(ignoredBase, callback) {
        // always give the caller something, even on error
        if (fxRates && fxTimestamp && (Date.now()/1000 - fxTimestamp) < 600) {
            callback(fxRates);
            return;
        }
        if (fetchingRates) {
            // queue another call after current fetch completes
            setTimeout(function() { fetchRates(ignoredBase, callback); }, 100);
            return;
        }
        fetchingRates = true;
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/api/fx-rates/?base=USD');
        xhr.onload = function () {
            fetchingRates = false;
            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    fxRates = data.rates;
                    fxBase = 'USD';
                    fxTimestamp = data.timestamp;
                    fxTimestampDisplay = data.timestamp_display;
                } catch (e) {
                    console.error('Invalid FX response', e);
                }
            } else {
                console.warn('FX request returned status', xhr.status);
            }
            // always call callback with whatever we have (cache or empty)
            callback(fxRates || {});
        };
        xhr.onerror = function () {
            fetchingRates = false;
            console.warn('FX rate fetch failed');
            callback(fxRates || {});
        };
        xhr.send();
    }

    function initDashboard(opts) {
        var totalBalance = opts.totalBalance;
        var friendBalances = opts.friendBalances;

        var toggle = document.getElementById('unified-toggle');
        var currencySelect = document.getElementById('unified-currency');
        var tsEl = document.getElementById('fx-timestamp');
        var currencySelectWrapper = document.getElementById('unified-select-wrapper');
        var rawFriendState = [];

        var friendItems = document.querySelectorAll('[data-friend-balance]');
        for (var si = 0; si < friendItems.length; si++) {
            var itemEl = friendItems[si];
            var labelNode = itemEl.querySelector('[data-balance-owe-label]');
            var valueNode = itemEl.querySelector('[data-balance-value]');
            rawFriendState[si] = {
                labelHtml: labelNode ? labelNode.innerHTML : '',
                valueHtml: valueNode ? valueNode.innerHTML : '',
                valueClass: valueNode ? valueNode.className : ''
            };
        }

        if (!toggle) return;

        function renderRaw(rates) {
            if (currencySelectWrapper) currencySelectWrapper.style.display = 'none';
            if (tsEl) tsEl.textContent = '';

            var totalEl = document.querySelector('[data-balance-type="total"]');
            if (totalEl) {
                totalEl.textContent = formatMultiRaw(totalBalance);
                var sign = rates ? detectSign(totalBalance, rates) : detectSignSimple(totalBalance);
                applyColor(totalEl, sign);
            }
            var totalLabel = document.querySelector('[data-balance-label="total"]');
            if (totalLabel) {
                var s = rates ? detectSign(totalBalance, rates) : detectSignSimple(totalBalance);
                totalLabel.textContent = s > 0 ? 'You are owed' : s < 0 ? 'You owe' : "You're all settled up";
            }

            var items = document.querySelectorAll('[data-friend-balance]');
            for (var i = 0; i < items.length; i++) {
                var row = items[i];
                var state = rawFriendState[i];
                if (!state) continue;
                var lbl = row.querySelector('[data-balance-owe-label]');
                var val = row.querySelector('[data-balance-value]');
                if (lbl) lbl.innerHTML = state.labelHtml;
                if (val) {
                    val.innerHTML = state.valueHtml;
                    val.className = state.valueClass;
                }
            }
        }

        function renderUnified(rates, targetCurrency) {
            if (currencySelectWrapper) currencySelectWrapper.style.display = '';
            if (tsEl) tsEl.textContent = 'Converted using live rate at ' + fxTimestampDisplay;

            var totalVal = computeUnified(totalBalance, targetCurrency, rates);
            var totalEl = document.querySelector('[data-balance-type="total"]');
            if (totalEl) {
                var totalText = formatAmount(totalVal, targetCurrency);
                if (totalVal > 0.005) totalText = '+ ' + totalText;
                totalEl.textContent = totalText;
                applyColor(totalEl, totalVal > 0.005 ? 1 : totalVal < -0.005 ? -1 : 0);
            }
            var totalLabel = document.querySelector('[data-balance-label="total"]');
            if (totalLabel) {
                totalLabel.textContent = totalVal > 0.005 ? 'You are owed' : totalVal < -0.005 ? 'You owe' : "You're all settled up";
            }

            var items = document.querySelectorAll('[data-friend-balance]');
            for (var i = 0; i < items.length; i++) {
                var el = items[i];
                var idx = parseInt(el.getAttribute('data-friend-balance'));
                var friend = friendBalances[idx];
                if (!friend) continue;

                var owesYouMap = friend.owed_to_user || {};
                var youOweMap = friend.owed_by_user || {};
                var owesYouUnified = computeUnified(owesYouMap, targetCurrency, rates);
                var youOweUnified = computeUnified(youOweMap, targetCurrency, rates);
                var balEl = el.querySelector('[data-balance-value]');
                var labelEl = el.querySelector('[data-balance-owe-label]');

                if (balEl) {
                    balEl.innerHTML = '';
                    balEl.classList.remove('balance-positive', 'balance-negative');
                    balEl.classList.add('balance-neutral');

                    if (owesYouUnified > 0.005) {
                        var owesSpan = document.createElement('div');
                        owesSpan.className = 'balance-positive';
                        owesSpan.textContent = formatAmount(owesYouUnified, targetCurrency);
                        balEl.appendChild(owesSpan);
                    }

                    if (youOweUnified > 0.005) {
                        var oweSpan = document.createElement('div');
                        oweSpan.className = 'balance-negative';
                        oweSpan.textContent = formatAmount(youOweUnified, targetCurrency);
                        balEl.appendChild(oweSpan);
                    }

                    if (owesYouUnified <= 0.005 && youOweUnified <= 0.005) {
                        var settledSpan = document.createElement('span');
                        settledSpan.className = 'balance-neutral';
                        settledSpan.textContent = '$0.00';
                        balEl.appendChild(settledSpan);
                    }
                }

                if (labelEl) {
                    labelEl.innerHTML = '';

                    if (owesYouUnified > 0.005) {
                        var owesLabel = document.createElement('div');
                        owesLabel.className = 'balance-positive';
                        owesLabel.textContent = 'Owes You: ' + formatAmount(owesYouUnified, targetCurrency);
                        labelEl.appendChild(owesLabel);
                    }

                    if (youOweUnified > 0.005) {
                        var oweLabel = document.createElement('div');
                        oweLabel.className = 'balance-negative';
                        oweLabel.textContent = 'You Owe: ' + formatAmount(youOweUnified, targetCurrency);
                        labelEl.appendChild(oweLabel);
                    }

                    if (owesYouUnified <= 0.005 && youOweUnified <= 0.005) {
                        var labelSpan = document.createElement('span');
                        labelSpan.className = 'balance-neutral';
                        labelSpan.textContent = 'settled';
                        labelEl.appendChild(labelSpan);
                    }
                }
            }
        }

        function update() {
            console.log('Dashboard update called, toggle=', toggle.checked);
            var container = document.getElementById('unified-matrix');
            if (container) container.innerHTML = '';

            if (toggle.checked) {
                var target = currencySelect ? currencySelect.value : 'USD';
                fetchRates(target, function (rates) {
                    renderUnified(rates, target);
                });
            } else {
                if (fxRates) {
                    renderRaw(fxRates);
                } else {
                    fetchRates('USD', function (rates) { renderRaw(rates); });
                }
            }
        }

        toggle.addEventListener('change', update);
        if (currencySelect) currencySelect.addEventListener('change', update);

        fetchRates('USD', function (rates) { renderRaw(rates); });
    }

    function initGroupDetail(opts) {
        console.log('initGroupDetail called', opts);
        var currentBalance = opts.currentBalance;
        var membersData = opts.members;
        var placeholderData = opts.placeholderMembers || [];
        var matrixData = opts.matrix;

        var toggle = document.getElementById('unified-toggle');
        var currencySelect = document.getElementById('unified-currency');
        var tsEl = document.getElementById('fx-timestamp');
        var currencySelectWrapper = document.getElementById('unified-select-wrapper');

        if (!toggle) return;

        function renderRaw(rates) {
            if (currencySelectWrapper) currencySelectWrapper.style.display = 'none';
            if (tsEl) tsEl.textContent = '';

            var userBalEl = document.querySelector('[data-balance-type="user-group"]');
            if (userBalEl) {
                userBalEl.textContent = formatMultiRaw(currentBalance);
                var sign = detectSign(currentBalance, rates);
                applyColor(userBalEl, sign);
            }
            var userLabel = document.querySelector('[data-balance-label="user-group"]');
            if (userLabel) {
                var s = detectSign(currentBalance, rates);
                userLabel.textContent = s > 0 ? 'You are owed' : s < 0 ? 'You owe' : "You're all settled up";
            }

            var memberEls = document.querySelectorAll('[data-member-balance]');
            for (var i = 0; i < memberEls.length; i++) {
                var el = memberEls[i];
                var idx = parseInt(el.getAttribute('data-member-balance'));
                var member = membersData[idx];
                if (!member) continue;
                el.textContent = formatMultiRaw(member.balances);
                var msign = detectSign(member.balances, rates);
                applyColor(el, msign);
            }
            // pending/placeholder members
            var placeholderEls = document.querySelectorAll('[data-placeholder-balance]');
            for (var i = 0; i < placeholderEls.length; i++) {
                var el = placeholderEls[i];
                var idx = parseInt(el.getAttribute('data-placeholder-balance'));
                var member = placeholderData[idx];
                if (!member) continue;
                el.textContent = formatMultiRaw(member.balances);
                var msign = detectSign(member.balances, rates);
                applyColor(el, msign);
            }

            var matrixEls = document.querySelectorAll('[data-matrix-item]');
            for (var j = 0; j < matrixEls.length; j++) {
                var mel = matrixEls[j];
                var midx = parseInt(mel.getAttribute('data-matrix-item'));
                var mitem = matrixData[midx];
                if (!mitem) continue;
                mel.textContent = sym(mitem.currency) + parseFloat(mitem.amount).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
            }
            var matrixRows = document.querySelectorAll('[data-matrix-row]');
            for (var k = 0; k < matrixRows.length; k++) {
                matrixRows[k].style.display = '';
            }
            // remove any unified representation if present
            var container = document.getElementById('unified-matrix');
            if (container) {
                container.innerHTML = '';
            }
        }

        function renderUnified(rates, targetCurrency) {
            if (currencySelectWrapper) currencySelectWrapper.style.display = '';
            if (tsEl) tsEl.textContent = 'Converted using live rate at ' + fxTimestampDisplay;

            var totalVal = computeUnified(currentBalance, targetCurrency, rates);
            var userBalEl = document.querySelector('[data-balance-type="user-group"]');
            if (userBalEl) {
                userBalEl.textContent = formatAmount(totalVal, targetCurrency);
                applyColor(userBalEl, totalVal > 0.005 ? 1 : totalVal < -0.005 ? -1 : 0);
            }
            var userLabel = document.querySelector('[data-balance-label="user-group"]');
            if (userLabel) {
                userLabel.textContent = totalVal > 0.005 ? 'You are owed' : totalVal < -0.005 ? 'You owe' : "You're all settled up";
            }
            // unify placeholder balances too
            var placeholderEls = document.querySelectorAll('[data-placeholder-balance]');
            for (var i = 0; i < placeholderEls.length; i++) {
                var el = placeholderEls[i];
                var idx = parseInt(el.getAttribute('data-placeholder-balance'));
                var member = placeholderData[idx];
                if (!member) continue;
                var val = computeUnified(member.balances, targetCurrency, rates);
                el.textContent = formatAmount(val, targetCurrency);
                var sign = val > 0.005 ? 1 : val < -0.005 ? -1 : 0;
                applyColor(el, sign);
            }

            var memberEls = document.querySelectorAll('[data-member-balance]');
            for (var i = 0; i < memberEls.length; i++) {
                var el = memberEls[i];
                var idx = parseInt(el.getAttribute('data-member-balance'));
                var member = membersData[idx];
                if (!member) continue;
                var val = computeUnified(member.balances, targetCurrency, rates);
                el.textContent = formatAmount(val, targetCurrency);
                applyColor(el, val > 0.005 ? 1 : val < -0.005 ? -1 : 0);
            }

            var merged = {};
            for (var j = 0; j < matrixData.length; j++) {
                var item = matrixData[j];
                var key = item.from_user_id + '|' + item.to_user_id;
                var reverseKey = item.to_user_id + '|' + item.from_user_id;
                var converted = convertAmount(parseFloat(item.amount), item.currency, targetCurrency, rates);
                if (merged[reverseKey]) {
                    merged[reverseKey].amount -= converted;
                } else {
                    if (!merged[key]) merged[key] = {from_id: item.from_user_id, from_name: item.from_user_name, to_id: item.to_user_id, to_name: item.to_user_name, amount: 0};
                    merged[key].amount += converted;
                }
            }

            var matrixRows = document.querySelectorAll('[data-matrix-row]');
            for (var k = 0; k < matrixRows.length; k++) {
                matrixRows[k].style.display = 'none';
            }

            var container = document.getElementById('unified-matrix');
            if (container) {
                container.innerHTML = '';
                for (var mkey in merged) {
                    if (!merged.hasOwnProperty(mkey)) continue;
                    var mitem = merged[mkey];
                    var fromName = mitem.from_name;
                    var toName = mitem.to_name;
                    var amt = mitem.amount;
                    if (Math.abs(amt) < 0.005) continue;
                    if (amt < 0) {
                        var tmp = fromName; fromName = toName; toName = tmp;
                        amt = Math.abs(amt);
                    }
                    amt = Math.round(amt * 100) / 100;
                    var row = document.createElement('div');
                    row.className = 'settlement-item';
                    row.innerHTML = '<div style="flex:1"><strong>' + escapeHtml(fromName) + '</strong></div>' +
                        '<div class="settlement-arrow">→</div>' +
                        '<div class="settlement-amount">' + formatAmount(amt, targetCurrency) + '</div>' +
                        '<div class="settlement-arrow">→</div>' +
                        '<div style="flex:1;text-align:right"><strong>' + escapeHtml(toName) + '</strong></div>';
                    container.appendChild(row);
                }
            }
        }

        function update() {
            // clear any existing unified matrix while we recompute
            var container = document.getElementById('unified-matrix');
            if (container) container.innerHTML = '';

            if (toggle.checked) {
                var target = currencySelect ? currencySelect.value : 'USD';
                fetchRates(target, function (rates) {
                    renderUnified(rates, target);
                });
            } else {
                if (fxRates) {
                    renderRaw(fxRates);
                } else {
                    fetchRates('USD', function (rates) { renderRaw(rates); });
                }
            }
        }

        toggle.addEventListener('change', update);
        if (currencySelect) currencySelect.addEventListener('change', update);

        fetchRates('USD', function (rates) { renderRaw(rates); });
    }

    function detectSignSimple(balances) {
        var total = 0;
        for (var code in balances) {
            if (!balances.hasOwnProperty(code)) continue;
            total += parseFloat(balances[code]);
        }
        if (total > 0.005) return 1;
        if (total < -0.005) return -1;
        return 0;
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    return {
        initDashboard: initDashboard,
        initGroupDetail: initGroupDetail
    };
})();
