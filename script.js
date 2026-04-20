const form = document.getElementById('mortgage-lead-form');
const message = document.querySelector('.form-message');
const yearNode = document.getElementById('year');

yearNode.textContent = new Date().getFullYear();

form.addEventListener('submit', (event) => {
  event.preventDefault();

  if (!form.checkValidity()) {
    message.textContent = 'Please complete all required fields with valid information.';
    message.className = 'form-message error';
    return;
  }

  const payload = Object.fromEntries(new FormData(form).entries());
  console.log('Lead captured:', payload);

  message.textContent = "Thanks! Your request has been received. We'll contact you soon.";
  message.className = 'form-message success';
  form.reset();
});
