import { useState, useEffect, useContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import AuthContext from '../context/AuthContext';
import ModalPortal from './ModalPortal'; 

const WAKEUP_MESSAGES = [
  "Spinning up eco-friendly standby container...",
  "Restoring PostgreSQL database into memory...",
  "Warming up global edge delivery networks...",
  "Synchronizing secure EazyShop product catalogs...",
  "Establishing zero-trust encrypted channels...",
  "Verifying SSL handshake and TLS protocols...",
  "Mounting persistent volume storage...",
  "Almost ready — booting application runtime..."
];

const ServerWakeup = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [isWaking, setIsWaking] = useState(false);
  const [currentMessage, setCurrentMessage] = useState("Initializing secure server environment...");

  // 1. Robust Server Polling Logic
  useEffect(() => {
    let isMounted = true;
    let pingInterval;

    const timeout = setTimeout(() => {
      if (isMounted) setIsWaking(true);
    }, 1000);

    const pingServer = async () => {
      try {
        await axiosInstance.get('/api/categories/'); 
        if (isMounted) {
          setIsWaking(false);
          clearTimeout(timeout);
          clearInterval(pingInterval);
        }
      } catch (err) {
        // Server is asleep; continue polling silently
      }
    };

    pingServer();
    pingInterval = setInterval(pingServer, 6000);

    return () => {
      isMounted = false;
      clearTimeout(timeout);
      clearInterval(pingInterval);
    };
  }, [axiosInstance]);

  // 2. Randomized Message Engine
  useEffect(() => {
    if (!isWaking) return;

    let isMounted = true;
    let timeoutId;
    let messageCount = 0;
    const shuffledMessages = [...WAKEUP_MESSAGES].sort(() => 0.5 - Math.random()).slice(0, 4);

    const scheduleNextMessage = () => {
      if (messageCount >= 4 || !isMounted) return;
      const randomDelay = Math.floor(Math.random() * (11000 - 6500 + 1) + 6500);

      timeoutId = setTimeout(() => {
        if (isMounted) {
          setCurrentMessage(shuffledMessages[messageCount]);
          messageCount++;
          scheduleNextMessage();
        }
      }, randomDelay);
    };

    scheduleNextMessage();

    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
    };
  }, [isWaking]);

  return (
    <AnimatePresence>
      {isWaking && (
        <ModalPortal>
          <Overlay 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
          >
            <GreenOrbTop />
            <GreenOrbBottom />

            <GlassModal
              initial={{ scale: 0.85, opacity: 0, y: 30 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.85, opacity: 0, y: 30 }}
              transition={{ type: "spring", stiffness: 250, damping: 25 }}
            >
              
              <SpinnerContainer>
                <OuterRing 
                  animate={{ rotate: 360 }} 
                  transition={{ duration: 12, repeat: Infinity, ease: "linear" }} 
                />
                
                <InnerRing 
                  animate={{ rotate: -360 }} 
                  transition={{ duration: 4, repeat: Infinity, ease: "linear" }} 
                />
                
                <CenterPulse
                  animate={{ scale: [1, 1.08, 1], boxShadow: ["0 0 15px rgba(16,185,129,0.3)", "0 0 35px rgba(16,185,129,0.7)", "0 0 15px rgba(16,185,129,0.3)"] }}
                  transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
                >
                  {/* 🚀 Using your custom logo asset */}
                  <LogoImg src="/android-chrome-512x512.png" alt="EazyShop Logo" />
                </CenterPulse>
              </SpinnerContainer>

              <TextContainer>
                <h2>Waking EazyShop Server</h2>
                <SubText>
                  Our eco-friendly backend instance spins down automatically during periods of inactivity to conserve cloud resources. Please hang tight for a moment while we spin it back online for you!
                </SubText>
                
                <MessageWrapper>
                  <AnimatePresence mode="wait">
                    <AnimatedMessage 
                      key={currentMessage}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -12 }}
                      transition={{ duration: 0.35 }}
                    >
                      {currentMessage}
                    </AnimatedMessage>
                  </AnimatePresence>
                </MessageWrapper>
              </TextContainer>

            </GlassModal>
          </Overlay>
        </ModalPortal>
      )}
    </AnimatePresence>
  );
};

// ==========================================
// ENTERPRISE GLASSMORPHISM STYLES
// ==========================================

const Overlay = styled(motion.div)`
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.75); 
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  display: flex; align-items: center; justify-content: center; z-index: 9999;
  padding: 1rem;
  overflow: hidden;
`;

const GreenOrbTop = styled.div`
  position: absolute; top: 10%; left: 15%; width: 450px; height: 450px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.4) 0%, transparent 70%);
  border-radius: 50%; pointer-events: none; z-index: 0; filter: blur(60px);
`;

const GreenOrbBottom = styled.div`
  position: absolute; bottom: 10%; right: 15%; width: 550px; height: 550px;
  background: radial-gradient(circle, rgba(11, 132, 87, 0.35) 0%, transparent 70%);
  border-radius: 50%; pointer-events: none; z-index: 0; filter: blur(70px);
`;

const GlassModal = styled(motion.div)`
  position: relative; z-index: 1;
  background: linear-gradient(135deg, rgba(209, 250, 229, 0.92) 0%, rgba(236, 253, 245, 0.85) 100%); 
  backdrop-filter: blur(30px);
  -webkit-backdrop-filter: blur(30px);
  padding: 3.5rem 2.5rem; 
  border-radius: 36px;
  max-width: 480px; width: 100%; 
  box-shadow: 0 40px 80px -20px rgba(11, 132, 87, 0.45), inset 0 2px 8px rgba(255,255,255,0.9);
  border: 1.5px solid rgba(16, 185, 129, 0.2);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  overflow: hidden;

  /* 🚀 Sleek inset curved border matching your markup */
  &::after {
    content: '';
    position: absolute;
    inset: 14px; /* Controls how far in the border sits from the outer edge */
    border: 1.5px solid rgba(16, 185, 129, 0.55); /* Site-themed green light border */
    border-radius: 26px; /* Smooth curved corners nested inside */
    pointer-events: none;
  }
`;

const SpinnerContainer = styled.div`
  position: relative;
  width: 140px;
  height: 140px;
  margin-bottom: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const OuterRing = styled(motion.div)`
  position: absolute;
  inset: 0;
  border: 3px dashed rgba(16, 185, 129, 0.45);
  border-radius: 50%;
`;

const InnerRing = styled(motion.div)`
  position: absolute;
  inset: 12px;
  border: 4px solid transparent;
  border-top: 4px solid #0B8457;
  border-right: 4px solid #10B981;
  border-radius: 50%;
  opacity: 0.9;
`;

const CenterPulse = styled(motion.div)`
  position: relative;
  width: 76px;
  height: 76px;
  background: #ffffff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 3px solid #10B981;
  z-index: 2;
  overflow: hidden;
  box-shadow: 0 8px 20px rgba(11, 132, 87, 0.2);
`;

const LogoImg = styled.img`
  width: 100%;
  height: 100%;
  object-fit: cover;
`;

const TextContainer = styled.div`
  width: 100%;
  
  h2 { 
    color: #0F172A; 
    font-size: 1.7rem; 
    margin: 0 0 0.75rem 0; 
    font-weight: 900; 
    letter-spacing: -0.5px; 
  }
`;

const SubText = styled.p`
  color: #475569;
  font-size: 0.9rem;
  line-height: 1.55;
  margin: 0 0 1.75rem 0;
  padding: 0 0.5rem;
`;

const MessageWrapper = styled.div`
  height: 2.5rem; 
  display: flex;
  align-items: center;
  justify-content: center;
  /* 🚀 Matching richer green background tint for the message box */
  background: rgba(16, 185, 129, 0.15);
  border-radius: 12px;
  border: 1px solid rgba(16, 185, 129, 0.35);
  padding: 0 1rem;
`;

const AnimatedMessage = styled(motion.p)`
  color: #0B8457; 
  font-size: 0.9rem; 
  font-weight: 700;
  line-height: 1.4; 
  margin: 0;
  width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export default ServerWakeup;