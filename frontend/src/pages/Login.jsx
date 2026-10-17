// src/pages/Login.jsx
import { useContext, useState } from 'react';
import AuthContext from '../context/AuthContext';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
// eslint-disable-next-line
import { toast, Toaster } from "react-hot-toast";
import styled from 'styled-components';
import { FaSignInAlt, FaLock } from 'react-icons/fa';
import FullScreenSpinner from '../components/FullScreenSpinner';
import AppLayout from '../components/AppLayout';
import {GlowingPageContainer } from '../styles/SharedPageStyles';

const Login = () => {
  const { loginUser } = useContext(AuthContext);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || '/';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true); 

    if (!email || !password) {
      setIsLoading(false);
      setTimeout(() => toast.error("❌ Please fill in all fields", { id: 'empty-fields' }), 250);
      return;
    }

    try {
      const success = await loginUser(email, password);

      if (success === true) {
        setTimeout(() => {
          toast.success('✅ Login successful!', { duration: 2000, id: 'login-success' });
          navigate(from);
        }, 1500); 
      } else if (typeof success === 'object') {
        const messages = Object.values(success).flat().join(' ');
        setErrorMsg(messages);
        setIsLoading(false);
        setTimeout(() => toast.error(messages || '❌ Login failed', { id: 'login-error' }), 250);
      } else {
        setErrorMsg('Invalid credentials');
        setIsLoading(false);
        setTimeout(() => toast.error('❌ Invalid credentials', { id: 'invalid-creds' }), 250);
      }
    } catch (err) {
      setErrorMsg('Unexpected error occurred');
      setIsLoading(false);
      setTimeout(() => toast.error('❌ An unexpected error occurred', { id: 'unexpected-error' }), 250);
    }
  };

  return (
    <>
      <AnimatePresence>
        {isLoading && <FullScreenSpinner message="Authenticating credentials..." />}
      </AnimatePresence>

      <AppLayout>
        <GlowingPageContainer $maxWidth="1100px">
          {/* 🚀 Nudged down slightly to match the register layout */}
          <AuthWrapper>
            <LoginCard
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 25 }}
            >
              <IconWrapper
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 300 }}
              >
                <FaLock size={22} />
              </IconWrapper>
              
              <Title>Welcome Back</Title>
              <Subtitle>Sign in to access your EazyShop account</Subtitle>
              
              <form onSubmit={handleSubmit}>
                <InputField
                  type="email"
                  placeholder="Email Address"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={isLoading}
                  whileFocus={{ scale: 1.02 }}
                />
                <InputField
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={isLoading}
                  whileFocus={{ scale: 1.02 }}
                />
                
                <ForgotPasswordContainer>
                  <Link to="/forgot-password">Forgot password?</Link>
                </ForgotPasswordContainer>

                <SubmitButton
                  type="submit"
                  disabled={isLoading}
                  whileHover={{ scale: isLoading ? 1 : 1.02 }}
                  whileTap={{ scale: isLoading ? 1 : 0.98 }}
                >
                  {isLoading ? 'Authenticating...' : <><FaSignInAlt /> Secure Login</>}
                </SubmitButton>
              </form>

              {errorMsg && (
                <ErrorText
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  {errorMsg}
                </ErrorText>
              )}

              <RegisterLink>
                Don't have an account? <Link to="/register" state={{ from }}>Create one now</Link>
              </RegisterLink>
            </LoginCard>
          </AuthWrapper>
        </GlowingPageContainer>
      </AppLayout>
    </>
  );
};

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const AuthWrapper = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 64vh; /* Pushes the card down precisely without creating a scrollbar */
  box-sizing: border-box;
`;

const LoginCard = styled(motion.div)`
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(11, 132, 87, 0.12);
  border-radius: 24px;
  box-shadow: 0 15px 40px -10px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 420px;
  text-align: center;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 1.75rem 2rem; 

  h1, h2 {
    margin-top: 0.4rem;
    margin-bottom: 0.2rem;
    font-size: 1.5rem;
  }

  p {
    margin-top: 0;
    margin-bottom: 1rem;
    font-size: 0.9rem;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem; 
  }

  @media (max-width: 768px) {
    padding: 1.25rem 1rem;
    width: 95%;
    background: rgba(255, 255, 255, 0.65);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-radius: 20px;
    box-shadow: 0 10px 30px -10px rgba(11, 132, 87, 0.1);
  }
`;

const IconWrapper = styled(motion.div)`
  background: #ECFDF5;
  color: #0B8457;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 0 5px rgba(16, 185, 129, 0.1);
  width: 42px;
  height: 42px;
  margin: 0 auto 0.5rem auto; 
  
  svg {
    width: 20px;
    height: 20px;
  }
`;

const Title = styled.h1`
  color: #0F172A;
  margin: 0 0 0.25rem 0;
  font-size: 1.6rem;
  font-weight: 900;
  letter-spacing: -0.5px;
`;

const Subtitle = styled.p`
  color: #64748B;
  font-size: 0.9rem;
  margin-bottom: 1.25rem;
`;

const InputField = styled(motion.input)`
  width: 100%;
  padding: 0.85rem 1rem;
  border: 1px solid #E2E8F0;
  background: #F8FAFC;
  border-radius: 12px;
  font-size: 0.95rem;
  color: #0F172A;
  transition: all 0.3s ease;
  box-sizing: border-box;

  &:focus {
    outline: none;
    background: #ffffff;
    border-color: #0B8457;
    box-shadow: 0 0 0 4px rgba(11, 132, 87, 0.1);
  }
`;

const ForgotPasswordContainer = styled.div`
  display: flex;
  justify-content: flex-end;
  margin-top: -0.2rem;
  margin-bottom: 0.2rem;

  a {
    color: #0B8457;
    font-size: 0.8rem;
    font-weight: 600;
    text-decoration: none;
    transition: color 0.2s ease;

    &:hover {
      color: #075E3E;
      text-decoration: underline;
    }
  }
`;

const SubmitButton = styled(motion.button)`
  width: 100%;
  padding: 0.9rem;
  background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 1rem;
  font-weight: 800;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 0.2rem;
  box-shadow: 0 4px 15px rgba(11, 132, 87, 0.25);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;

  &:hover:not(:disabled) { box-shadow: 0 6px 20px rgba(11, 132, 87, 0.4); }
  &:disabled { opacity: 0.7; cursor: not-allowed; }
`;

const ErrorText = styled(motion.p)`
  color: #DC2626;
  background: #FEF2F2;
  padding: 0.6rem;
  border-radius: 8px;
  border: 1px solid #FCA5A5;
  font-size: 0.85rem;
  font-weight: 600;
  margin-top: 1rem;
`;

const RegisterLink = styled.div`
  margin-top: 1.25rem;
  color: #64748B;
  font-size: 0.9rem;

  a {
    color: #0B8457;
    text-decoration: none;
    font-weight: 700;
    margin-left: 4px;
    transition: color 0.2s ease;

    &:hover { color: #075E3E; text-decoration: underline; }
  }
`;

export default Login;