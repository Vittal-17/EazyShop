// src/styles/SharedPageStyles.js
import styled from 'styled-components';
import { motion } from 'framer-motion';

// 🚀 1. Universal Inner Container 
// Keeps your content perfectly centered and contained within the glass canvas
export const PageContainer = styled.div`
  position: relative;
  z-index: 1;
  max-width: 1250px; 
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
`;

// 🚀 2. Universal Page Header
// Gives every page (Cart, Wishlist, Store) a consistent, high-end SaaS title
export const PageHeader = styled(motion.div)`
  text-align: center;
  margin-bottom: 2.5rem;
  padding: 0 1rem;
  
  h1 {
    font-size: clamp(2.2rem, 4vw, 3rem);
    font-weight: 900;
    color: #0F172A; /* Deep slate for high contrast on frosted glass */
    margin-bottom: 0.5rem;
    letter-spacing: -1px;
  }
  
  p {
    color: #64748B;
    font-size: 1.1rem;
    max-width: 600px;
    margin: 0 auto;
    line-height: 1.5;
  }
`;

// 🚀 3. Universal Empty State Card
// Perfect for "Cart is Empty", "No Wishlist Items", or "No Orders Found"
export const EmptyStateCard = styled(motion.div)`
  text-align: center; 
  padding: 5rem 2rem; 
  background: rgba(255, 255, 255, 0.5); /* Semi-transparent to let the glass show through */
  border-radius: 24px; 
  border: 1px dashed #CBD5E1;
  max-width: 600px;
  margin: 2rem auto;
  
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; margin-bottom: 1.5rem; }
  
  .primary-action {
    margin-top: 1.5rem;
    background: #0B8457;
    color: white;
    border: none;
    padding: 0.8rem 1.8rem;
    border-radius: 50px;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.2s;
    text-decoration: none;
    display: inline-block;
    
    &:hover { background: #086341; }
  }
`;

export const GlowingPageContainer = styled.div`
  position: relative;
  z-index: 1;
  /* 🚀 Dynamic width so it adapts perfectly to any page layout */
  max-width: ${props => props.$maxWidth || '1500px'}; 
  margin: 0 auto;
  padding: 0 2.5rem;
  box-sizing: border-box;

  /* 🔥 THE 12-ORB SCATTERED AMBIENT ENGINE */
  &::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    z-index: -1;
    pointer-events: none;
    filter: blur(65px); 

    background: 
      /* --- TOP CLUSTER --- */
      radial-gradient(circle at -2% 2%, rgba(11, 132, 87, 0.45) 0%, transparent 550px),
      radial-gradient(circle at 102% 8%, rgba(16, 185, 129, 0.45) 0%, transparent 600px),
      radial-gradient(circle at 25% 12%, rgba(11, 132, 87, 0.20) 0%, transparent 400px),
      
      /* --- UPPER-MID CLUSTER --- */
      radial-gradient(circle at 85% 25%, rgba(16, 185, 129, 0.25) 0%, transparent 500px),
      radial-gradient(circle at -5% 35%, rgba(16, 185, 129, 0.40) 0%, transparent 600px),
      radial-gradient(circle at 40% 42%, rgba(11, 132, 87, 0.15) 0%, transparent 450px),
      
      /* --- LOWER-MID CLUSTER --- */
      radial-gradient(circle at 105% 55%, rgba(11, 132, 87, 0.35) 0%, transparent 550px),
      radial-gradient(circle at 15% 65%, rgba(16, 185, 129, 0.20) 0%, transparent 400px),
      radial-gradient(circle at 90% 72%, rgba(11, 132, 87, 0.25) 0%, transparent 500px),
      
      /* --- BOTTOM CLUSTER --- */
      radial-gradient(circle at -2% 85%, rgba(11, 132, 87, 0.45) 0%, transparent 600px),
      radial-gradient(circle at 102% 95%, rgba(16, 185, 129, 0.45) 0%, transparent 550px),
      radial-gradient(circle at 35% 92%, rgba(16, 185, 129, 0.20) 0%, transparent 450px);
      
    background-repeat: no-repeat;
  }

  /* 🚀 BULLETPROOF MOBILE SCALING */
  @media (max-width: 768px) {
    padding: 0 1rem;
    margin-top: 1rem; 
    
    &::before {
      filter: blur(50px);
      
      background: 
        radial-gradient(circle at -15% 2%, rgba(11, 132, 87, 0.40) 0%, transparent 300px),
        radial-gradient(circle at 115% 8%, rgba(16, 185, 129, 0.40) 0%, transparent 350px),
        radial-gradient(circle at 25% 12%, rgba(11, 132, 87, 0.15) 0%, transparent 200px),
        
        radial-gradient(circle at 85% 25%, rgba(16, 185, 129, 0.15) 0%, transparent 250px),
        radial-gradient(circle at -10% 35%, rgba(16, 185, 129, 0.35) 0%, transparent 300px),
        radial-gradient(circle at 40% 42%, rgba(11, 132, 87, 0.10) 0%, transparent 200px),
        
        radial-gradient(circle at 110% 55%, rgba(11, 132, 87, 0.30) 0%, transparent 300px),
        radial-gradient(circle at 15% 65%, rgba(16, 185, 129, 0.15) 0%, transparent 250px),
        radial-gradient(circle at 90% 72%, rgba(11, 132, 87, 0.15) 0%, transparent 250px),
        
        radial-gradient(circle at -10% 85%, rgba(11, 132, 87, 0.40) 0%, transparent 350px),
        radial-gradient(circle at 110% 95%, rgba(16, 185, 129, 0.40) 0%, transparent 300px),
        radial-gradient(circle at 35% 92%, rgba(16, 185, 129, 0.15) 0%, transparent 200px);
    }
  }
`;