import { createPortal } from 'react-dom'; // 🚀 Import React Portal
import styled from 'styled-components';
import { motion } from 'framer-motion';

const Overlay = styled(motion.div)`
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 999999; /* 🚀 Maxed out z-index */
  pointer-events: all; 
`;

const SpinnerCircle = styled(motion.div)`
  width: 65px;
  height: 65px;
  border: 5px solid #e8f5e9;
  border-top: 5px solid #2e7d32;
  border-radius: 50%;
  box-shadow: 0 4px 15px rgba(46, 125, 50, 0.15);
`;

const LoadingText = styled(motion.p)`
  margin-top: 1.5rem;
  color: #2e7d32;
  font-weight: 700;
  font-size: 1.2rem;
  font-family: inherit;
  letter-spacing: 0.5px;
`;

const FullScreenSpinner = ({ message = "Authenticating..." }) => {
  // 🚀 Teleport the spinner directly to the <body> tag to prevent CSS trapping!
  return createPortal(
    <Overlay
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      <SpinnerCircle
        animate={{ rotate: 360 }}
        transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
      />
      <LoadingText
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        {message}
      </LoadingText>
    </Overlay>,
    document.body // <-- The magic happens right here
  );
};

export default FullScreenSpinner;