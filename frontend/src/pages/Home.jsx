// src/pages/Home.jsx
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { motion } from 'framer-motion';
import homeBgImage from '../assets/home.jpg'; 

const Home = () => {
  const navigate = useNavigate();

  return (
    <HeroContainer>
      <BackgroundWrapper>
        <BackgroundImage src={homeBgImage} alt="EazyShop 3D eCommerce" />
      </BackgroundWrapper>
      
      <GlassCard
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        <HeroTitle 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5, type: "spring", stiffness: 300, damping: 24 }}
        >
          Welcome to EazyShop
        </HeroTitle>
        
        <Subtitle 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.5, type: "spring", stiffness: 300, damping: 24 }}
        >
          Discover curated collections and experience effortless shopping with our seamless platform.
        </Subtitle>
        
        <CTAButton 
          onClick={() => navigate('/products')}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5, duration: 0.5, type: "spring", stiffness: 300, damping: 24 }}
          whileHover={{ scale: 1.05, y: -2 }}
          whileTap={{ scale: 0.95 }}
        >
          <span className="icon">🛍️</span> Start Shopping
        </CTAButton>
      </GlassCard>
    </HeroContainer>
  );
};

// --- STYLED COMPONENTS ---

const HeroContainer = styled.div`
  position: relative;
  width: 100%;
  min-height: 100vh; 
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding-top: 76px;
  box-sizing: border-box;
`;

const BackgroundWrapper = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  filter: blur(4px);
  transform: scale(1.02);
`;

const BackgroundImage = styled.img`
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.9; 
  display: block; 
`;

const GlassCard = styled(motion.div)`
  position: relative;
  z-index: 1;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 24px;
  padding: 4rem 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  width: 90%;
  max-width: 850px;
  box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1);
  will-change: transform, opacity;
  box-sizing: border-box;

  /* 🚀 MOBILE FIX: Reclaim horizontal screen real estate */
  @media (max-width: 768px) {
    padding: 2.5rem 1.25rem;
    width: 92%;
    border-radius: 20px;
  }
`;

const HeroTitle = styled(motion.h1)`
  /* 🚀 MOBILE FIX: Lowered the minimum font size from 3rem to 2.2rem so it scales down on small phones */
  font-size: clamp(2.2rem, 8vw, 4.5rem);
  font-weight: 900;
  color: #0B8457; 
  margin-bottom: 1.2rem;
  letter-spacing: -1px;
  position: relative;
  z-index: 2;
  word-wrap: break-word; /* Prevents long words from breaking the container */
  
  @media (max-width: 768px) {
    margin-bottom: 0.8rem;
  }
`;

const Subtitle = styled(motion.p)`
  font-size: clamp(0.95rem, 2vw, 1.15rem);
  color: #1a1a1a;
  margin-bottom: 2.5rem;
  font-weight: 600;
  line-height: 1.6;
  max-width: 600px;
  position: relative;
  z-index: 2;

  /* 🚀 MOBILE FIX: Slightly tighten margins for smaller screens */
  @media (max-width: 768px) {
    margin-bottom: 2rem;
    padding: 0 0.5rem;
  }
`;

const CTAButton = styled(motion.button)`
  background: #0B8457; 
  color: white;
  border: none;
  padding: 1rem 2.5rem;
  font-size: 1.15rem;
  font-weight: 700;
  border-radius: 50px;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(11, 132, 87, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  position: relative;
  overflow: hidden;
  z-index: 2;
  
  .icon {
    font-size: 1.2rem;
    z-index: 2;
  }
  
  /* Liquid Shimmer Effect */
  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: -150%;
    width: 50%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
    transform: skewX(-25deg);
    animation: shimmer 4s infinite;
    z-index: 1;
  }
  
  @keyframes shimmer {
    0% { left: -150%; }
    20% { left: 200%; }
    100% { left: 200%; }
  }
  
  &:hover {
    background: #096b46;
    box-shadow: 0 8px 20px rgba(11, 132, 87, 0.5);
  }
`;

export default Home;