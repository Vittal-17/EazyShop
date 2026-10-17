// src/components/ModalPortal.jsx
import { createPortal } from 'react-dom';

const ModalPortal = ({ children }) => {
  // Renders the modal directly into the body, bypassing CSS backdrop-filter traps
  return createPortal(children, document.body);
};

export default ModalPortal;