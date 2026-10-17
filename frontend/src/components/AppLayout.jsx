// src/components/AppLayout.jsx
import styled from 'styled-components';

const AppLayout = ({ children }) => {
  return (
    <PageWrapper>
      <TopFadeMask />
      <LeftMarginGlow />
      <RightMarginGlow />
      <TechGridBackground />
      <AppCanvasContainer>
        {children}
      </AppCanvasContainer>
    </PageWrapper>
  );
};

export default AppLayout;

// ==========================================
// GLOBAL GLASSMORPHIC STYLES
// ==========================================

const PageWrapper = styled.div`
  position: relative;
  min-height: 100vh;
  
  /* 🚀 THE FIX: Change 100vw to 100% */
  width: 100%; 
  
  background: linear-gradient(135deg, #F1F5F9 0%, #E2E8F0 50%, #CBD5E1 100%);
  padding-top: 100px;
  padding-bottom: 5rem;
  padding-left: 2rem;
  padding-right: 2rem;
  box-sizing: border-box;
  overflow-x: hidden;
  display: flex;
  justify-content: center;

  /* 🚀 Mobile Fix: Remove horizontal padding to let the canvas touch the edges */
  @media (max-width: 768px) {
    padding-left: 0;
    padding-right: 0;
    padding-top: 80px; 
    padding-bottom: 0;
  }
`;

const AppCanvasContainer = styled.div`
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1450px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.95);
  border-radius: 32px;
  padding: 2.5rem 2rem;
  box-shadow: 0 30px 60px rgba(15, 23, 42, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.8);
  box-sizing: border-box;
  margin-bottom: 3rem;

  /* 🚀 Mobile Fix: Edge-to-edge native app feel, BUT KEEP THE GLASS */
    @media (max-width: 768px) {
      border-radius: 24px 24px 0 0; 
      padding: 1.5rem 1rem;
      margin-bottom: 0;
      min-height: calc(100vh - 80px); 
      
      /* 🔥 THE GLASS RESTORATION 🔥 */
      background: rgba(255, 255, 255, 0.70); /* Slightly more transparent to see the grid */
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      
      /* Only keep the top border to mimic a glass sheet sliding up */
      border-top: 1px solid rgba(255, 255, 255, 0.9);
      border-left: none;
      border-right: none;
      border-bottom: none;
      
      /* Soft upward glow to separate it from the background */
      box-shadow: 0 -10px 40px rgba(11, 132, 87, 0.08); 
    }
`;

const TechGridBackground = styled.div`
  position: fixed;
  inset: 0;
  background-image: 
    linear-gradient(to right, rgba(11, 132, 87, 0.03) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(11, 132, 87, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
  z-index: 0;
`;

const LeftMarginGlow = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  width: 400px;
  height: 100vh;
  background: radial-gradient(circle at 0% 50%, rgba(11, 132, 87, 0.22) 0%, rgba(16, 185, 129, 0.08) 40%, transparent 70%);
  pointer-events: none;
  z-index: 0;
  filter: blur(40px);

  @media (max-width: 768px) {
    width: 200px; /* Reduce glow intensity on small screens */
  }
`;

const RightMarginGlow = styled.div`
  position: fixed;
  top: 0;
  right: 0;
  width: 400px;
  height: 100vh;
  background: radial-gradient(circle at 100% 50%, rgba(16, 185, 129, 0.22) 0%, rgba(11, 132, 87, 0.08) 40%, transparent 70%);
  pointer-events: none;
  z-index: 0;
  filter: blur(40px);

  @media (max-width: 768px) {
    width: 200px;
  }
`;

const TopFadeMask = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 110px; /* Tall enough to cover the floating gap and navbar zone */
  background: linear-gradient(
    to bottom, 
    #F1F5F9 0%, 
    rgba(241, 245, 249, 0.8) 50%, 
    rgba(241, 245, 249, 0) 100%
  );
  pointer-events: none; /* Allows mouse clicks to pass right through it */
  z-index: 999; /* Sits right below the Navbar (z-index: 1000) and above the content */
  
  @media (max-width: 768px) {
    height: 90px;
  }
`;