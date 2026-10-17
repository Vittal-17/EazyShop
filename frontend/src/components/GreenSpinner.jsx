import styled from 'styled-components';
import { motion } from 'framer-motion';

const SpinnerWrapper = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
`;

const SpinningCircle = styled(motion.div)`
  width: 22px;
  height: 22px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-top: 3px solid #ffffff;
  border-radius: 50%;
`;

const GreenSpinner = () => (
  <SpinnerWrapper>
    <SpinningCircle
      animate={{ rotate: 360 }}
      transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
    />
  </SpinnerWrapper>
);

export default GreenSpinner;