const API_URL = window.location.protocol === 'file:' ? 'http://localhost:8000' : window.location.origin;

document.getElementById('loginForm').addEventListener('submit', async (event) => {
    event.preventDefault();

    const usuario = document.getElementById('usuario').value;
    const senha = document.getElementById('senha').value;
    const errorMessageDiv = document.getElementById('errorMessage');
    const submitButton = event.target.querySelector('button');

    errorMessageDiv.style.display = 'none';
    submitButton.disabled = true;
    submitButton.textContent = 'Entrando...';

    try {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ usuario, senha }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Credenciais inválidas');
        }

        const data = await response.json();
        
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('nome', data.usuario.nome);

        window.location.href = 'admin.html';

    } catch (error) {
        errorMessageDiv.textContent = error.message;
        errorMessageDiv.style.display = 'block';
        submitButton.disabled = false;
        submitButton.textContent = 'Entrar';
    }
});

// Lógica de Recuperação de Senha
const modal = document.getElementById('recoveryModal');
const modalContent = modal.querySelector('.modal-content');
const forgotBtn = document.getElementById('forgotBtn');
const closeRecovery = document.getElementById('closeRecovery');
const sendRecovery = document.getElementById('sendRecovery');

forgotBtn.addEventListener('click', (e) => {
    e.preventDefault();
    modal.style.display = 'flex';
    if (window.gsap) {
        gsap.to(modal, { opacity: 1, duration: 0.3 });
        gsap.fromTo(modalContent, { scale: 0.9 }, { scale: 1, duration: 0.3, ease: 'back.out(1.2)' });
    } else {
        modal.style.opacity = 1;
    }
});

closeRecovery.addEventListener('click', () => {
    if (window.gsap) {
        gsap.to(modal, { opacity: 0, duration: 0.3, onComplete: () => modal.style.display = 'none' });
        gsap.to(modalContent, { scale: 0.9, duration: 0.3 });
    } else {
        modal.style.display = 'none';
    }
});

sendRecovery.addEventListener('click', async () => {
    const email = document.getElementById('recoveryEmail').value;
    if (!email) return alert('Digite um e-mail válido');

    sendRecovery.textContent = 'Enviando...';
    try {
        await fetch(`${API_URL}/auth/recuperar-senha`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        alert('Se o e-mail existir, as instruções foram enviadas.');
        modal.style.display = 'none';
    } catch (e) {
        alert('Erro ao conectar com o servidor');
    } finally {
        sendRecovery.textContent = 'Enviar';
    }
});