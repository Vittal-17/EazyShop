import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { motion } from 'framer-motion';

const NotFound = () => {
  const navigate = useNavigate();

  return (
    <Container>
      <GlowOrb />
      <Card
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      >
        <Badge
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.15, type: 'spring', stiffness: 300, damping: 20 }}
        >
          404 Error
        </Badge>

        <Heading>Page Not Found</Heading>

        <Description>
          Sorry, the page you are looking for doesn't exist, has been removed, or is temporarily unavailable.
        </Description>

        <ButtonGroup>
          <PrimaryButton
            onClick={() => navigate('/')}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
          >
            Return to Home
          </PrimaryButton>

          <SecondaryButton
            onClick={() => navigate('/products')}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
          >
            Browse Products
          </SecondaryButton>
        </ButtonGroup>
      </Card>
    </Container>
  );
};

// --- STYLED COMPONENTS ---

const Container = styled.div`
  position: relative;
  min-height: calc(100vh - 76px);
  margin-top: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1rem;
  box-sizing: border-box;
  overflow: hidden;
  background: radial-gradient(circle at top, #f8fafc 0%, #e2e8f0 100%);
`;

const GlowOrb = styled.div`
  position: absolute;
  width: 500px;
  height: 500px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.25) 0%, transparent 70%);
  filter: blur(80px);
  pointer-events: none;
`;

const Card = styled(motion.div)`
  position: relative;
  z-index: 1;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 20px 40px -15px rgba(11, 132, 87, 0.15), 0 0 1px rgba(0, 0, 0, 0.08);
  border-radius: 28px;
  padding: 3.5rem 2.5rem;
  max-width: 520px;
  width: 100%;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
`;

const Badge = styled(motion.div)`
  display: inline-block;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(11, 132, 87, 0.2));
  color: #0b8457;
  font-weight: 800;
  font-size: 0.9rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 0.4rem 1.2rem;
  border-radius: 9999px;
  border: 1px solid rgba(16, 185, 129, 0.3);
  margin-bottom: 1.25rem;
`;

const Heading = styled.h1`
  color: #0f172a;
  font-size: 2.25rem;
  font-weight: 800;
  margin: 0 0 1rem 0;
  letter-spacing: -0.5px;
`;

const Description = styled.p`
  color: #475569;
  font-size: 1rem;
  line-height: 1.6;
  margin: 0 0 2.25rem 0;
  max-width: 420px;
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
  width: 100%;
`;

const PrimaryButton = styled(motion.button)`
  background: linear-gradient(135deg, #0b8457, #10b981);
  color: #ffffff;
  border: none;
  padding: 0.85rem 1.75rem;
  border-radius: 14px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(11, 132, 87, 0.35);
  transition: box-shadow 0.2s ease;

  &:hover {
    box-shadow: 0 6px 20px rgba(11, 132, 87, 0.45);
  }
`;

const SecondaryButton = styled(motion.button)`
  background: transparent;
  color: #0f172a;
  border: 1.5px solid #cbd5e1;
  padding: 0.85rem 1.75rem;
  border-radius: 14px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: rgba(241, 245, 249, 0.8);
    border-color: #94a3b8;
  }
`;

export default NotFound;
