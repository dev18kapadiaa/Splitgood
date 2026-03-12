// Splitgood - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss messages after 5 seconds
    const messages = document.querySelectorAll('.message');
    messages.forEach(function(message) {
        setTimeout(function() {
            message.style.opacity = '0';
            message.style.transform = 'translateY(-10px)';
            setTimeout(function() {
                message.remove();
            }, 300);
        }, 5000);
    });

    // Tab functionality
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            const tabGroup = this.closest('.tabs-container');
            const targetId = this.dataset.tab;
            
            // Update tab states
            tabGroup.querySelectorAll('.tab').forEach(function(t) {
                t.classList.remove('active');
            });
            this.classList.add('active');
            
            // Update content visibility
            tabGroup.querySelectorAll('.tab-content').forEach(function(content) {
                content.classList.remove('active');
            });
            document.getElementById(targetId).classList.add('active');
        });
    });

    // Split type toggle
    const splitTypeSelect = document.getElementById('id_split_type');
    if (splitTypeSelect) {
        splitTypeSelect.addEventListener('change', function() {
            const unequalFields = document.querySelector('.unequal-split-fields');
            if (unequalFields) {
                if (this.value === 'equal') {
                    unequalFields.classList.add('hidden');
                } else {
                    unequalFields.classList.remove('hidden');
                    calculateEqualShares();
                }
            }
        });
    }

    // Calculate equal shares on amount change
    const totalAmountInput = document.getElementById('id_total_amount');
    if (totalAmountInput) {
        totalAmountInput.addEventListener('input', calculateEqualShares);
    }

    // Participant checkbox changes
    const participantCheckboxes = document.querySelectorAll('.participant-checkbox');
    participantCheckboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', calculateEqualShares);
    });

    // Form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner"></span> Processing...';
            }
        });
    });
});

// Calculate equal shares for participants
function calculateEqualShares() {
    const totalAmountInput = document.getElementById('id_total_amount');
    const splitTypeSelect = document.getElementById('id_split_type');
    
    if (!totalAmountInput || !splitTypeSelect) return;
    
    const totalAmount = parseFloat(totalAmountInput.value) || 0;
    const selectedParticipants = document.querySelectorAll('.participant-checkbox:checked');
    
    if (splitTypeSelect.value === 'equal' && selectedParticipants.length > 0) {
        const shareAmount = (totalAmount / selectedParticipants.length).toFixed(2);
        
        // Update display if exists
        const shareDisplay = document.querySelector('.equal-share-display');
        if (shareDisplay) {
            shareDisplay.textContent = '$' + shareAmount + ' each';
        }
    }
    
    // For unequal splits, initialize fields with equal amounts
    if (splitTypeSelect.value !== 'equal') {
        const splitAmountInputs = document.querySelectorAll('.split-amount');
        if (selectedParticipants.length > 0 && totalAmount > 0) {
            const shareAmount = (totalAmount / selectedParticipants.length).toFixed(2);
            
            splitAmountInputs.forEach(function(input) {
                const userId = input.dataset.userId;
                const checkbox = document.querySelector('.participant-checkbox[value="' + userId + '"]');
                if (checkbox && checkbox.checked && input.value === '0') {
                    input.value = shareAmount;
                }
            });
        }
    }
    
    // Update total display for unequal splits
    updateUnequalTotal();
}

// Update total for unequal splits
function updateUnequalTotal() {
    const splitAmountInputs = document.querySelectorAll('.split-amount');
    const totalDisplay = document.querySelector('.unequal-total');
    const totalAmountInput = document.getElementById('id_total_amount');
    
    if (!totalDisplay || !totalAmountInput) return;
    
    let sum = 0;
    splitAmountInputs.forEach(function(input) {
        sum += parseFloat(input.value) || 0;
    });
    
    const totalAmount = parseFloat(totalAmountInput.value) || 0;
    const diff = (sum - totalAmount).toFixed(2);
    
    totalDisplay.textContent = '$' + sum.toFixed(2);
    
    const diffDisplay = document.querySelector('.unequal-diff');
    if (diffDisplay) {
        if (Math.abs(diff) < 0.01) {
            diffDisplay.textContent = '';
            diffDisplay.className = 'unequal-diff';
        } else if (diff > 0) {
            diffDisplay.textContent = '($' + Math.abs(diff) + ' over)';
            diffDisplay.className = 'unequal-diff balance-negative';
        } else {
            diffDisplay.textContent = '($' + Math.abs(diff) + ' remaining)';
            diffDisplay.className = 'unequal-diff balance-negative';
        }
    }
}

// Add event listeners to split amount inputs
document.addEventListener('DOMContentLoaded', function() {
    const splitAmountInputs = document.querySelectorAll('.split-amount');
    splitAmountInputs.forEach(function(input) {
        input.addEventListener('input', updateUnequalTotal);
    });
});

// Confirm delete
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this item?');
}

// Quick settle button
function quickSettle(fromUserId, toUserId, amount) {
    const form = document.getElementById('settle-form');
    if (form) {
        document.getElementById('id_from_user').value = fromUserId;
        document.getElementById('id_to_user').value = toUserId;
        document.getElementById('id_amount').value = amount;
        
        // Scroll to form
        form.scrollIntoView({ behavior: 'smooth' });
    }
}
