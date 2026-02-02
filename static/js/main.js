// Write It Great - Proposal Evaluation System JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const form = document.getElementById('proposal-form');
    const fileInput = document.getElementById('proposal_file');
    const fileUploadDisplay = document.querySelector('.file-upload-display');
    const fileSelected = document.querySelector('.file-selected');
    const fileName = document.querySelector('.file-name');
    const removeFileBtn = document.querySelector('.remove-file');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoading = submitBtn.querySelector('.btn-loading');
    const errorMessage = document.getElementById('error-message');
    const errorText = errorMessage.querySelector('.error-text');
    
    // Modals
    const termsModal = document.getElementById('terms-modal');
    const ndaModal = document.getElementById('nda-modal');
    const termsLink = document.getElementById('terms-link');
    const ndaLink = document.getElementById('nda-link');
    
    // File Upload Handling
    fileInput.addEventListener('change', function(e) {
        if (this.files && this.files[0]) {
            const file = this.files[0];
            
            // Validate file type
            if (!file.name.toLowerCase().endsWith('.pdf')) {
                showError('Please upload a PDF file only.');
                this.value = '';
                return;
            }
            
            // Validate file size (50MB)
            if (file.size > 50 * 1024 * 1024) {
                showError('File size must be less than 50MB.');
                this.value = '';
                return;
            }
            
            // Show selected file
            fileName.textContent = file.name;
            fileUploadDisplay.style.display = 'none';
            fileSelected.style.display = 'flex';
            hideError();
        }
    });
    
    // Remove file
    removeFileBtn.addEventListener('click', function(e) {
        e.preventDefault();
        fileInput.value = '';
        fileUploadDisplay.style.display = 'block';
        fileSelected.style.display = 'none';
    });
    
    // Drag and drop
    const dropZone = document.querySelector('.file-upload-wrapper');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });
    
    function highlight() {
        fileUploadDisplay.style.borderColor = '#c9a962';
        fileUploadDisplay.style.background = '#fff';
    }
    
    function unhighlight() {
        fileUploadDisplay.style.borderColor = '#e0e0e0';
        fileUploadDisplay.style.background = '#f5f5f5';
    }
    
    dropZone.addEventListener('drop', handleDrop, false);
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            fileInput.files = files;
            fileInput.dispatchEvent(new Event('change'));
        }
    }
    
    // Modal Handling
    termsLink.addEventListener('click', function(e) {
        e.preventDefault();
        termsModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    });
    
    ndaLink.addEventListener('click', function(e) {
        e.preventDefault();
        ndaModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    });
    
    document.querySelectorAll('.modal-close, .modal-close-btn').forEach(btn => {
        btn.addEventListener('click', closeModals);
    });
    
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeModals();
            }
        });
    });
    
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeModals();
        }
    });
    
    function closeModals() {
        termsModal.classList.remove('active');
        ndaModal.classList.remove('active');
        document.body.style.overflow = '';
    }
    
    // Form Submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // Validate
        if (!validateForm()) {
            return;
        }
        
        // Show loading state
        setLoading(true);
        hideError();
        
        try {
            const formData = new FormData(form);
            
            const response = await fetch('/api/evaluate', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'An error occurred during evaluation');
            }
            
            // Success - redirect to results page
            window.location.href = `/results/${data.submission_id}`;
            
        } catch (error) {
            showError(error.message);
            setLoading(false);
        }
    });
    
    function validateForm() {
        const authorName = document.getElementById('author_name').value.trim();
        const authorEmail = document.getElementById('author_email').value.trim();
        const bookTitle = document.getElementById('book_title').value.trim();
        const proposalType = document.querySelector('input[name="proposal_type"]:checked');
        const agreeTerms = document.getElementById('agree_terms').checked;
        const agreeNda = document.getElementById('agree_nda').checked;
        const file = fileInput.files[0];
        
        if (!authorName) {
            showError('Please enter your name.');
            return false;
        }
        
        if (!authorEmail || !isValidEmail(authorEmail)) {
            showError('Please enter a valid email address.');
            return false;
        }
        
        if (!bookTitle) {
            showError('Please enter your book title.');
            return false;
        }
        
        if (!proposalType) {
            showError('Please select the type of proposal you are submitting.');
            return false;
        }
        
        if (!file) {
            showError('Please upload your proposal PDF.');
            return false;
        }
        
        if (!agreeTerms) {
            showError('You must agree to the Terms and Conditions.');
            return false;
        }
        
        if (!agreeNda) {
            showError('You must agree to the Non-Disclosure Agreement.');
            return false;
        }
        
        return true;
    }
    
    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
    
    function setLoading(loading) {
        submitBtn.disabled = loading;
        btnText.style.display = loading ? 'none' : 'inline';
        btnLoading.style.display = loading ? 'inline-flex' : 'none';
    }
    
    function showError(message) {
        errorText.textContent = message;
        errorMessage.style.display = 'flex';
        errorMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    function hideError() {
        errorMessage.style.display = 'none';
    }
});
