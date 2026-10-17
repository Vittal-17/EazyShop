// src/pages/Register.jsx
import { useState, useEffect, useContext } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
// eslint-disable-next-line
import { toast, Toaster } from "react-hot-toast";
import AuthContext from '../context/AuthContext';
import styled from 'styled-components';
import { FaUserPlus, FaCheckCircle, FaCircle } from 'react-icons/fa';
import FullScreenSpinner from '../components/FullScreenSpinner'; 
import AppLayout from '../components/AppLayout';
import {GlowingPageContainer } from '../styles/SharedPageStyles';

const API_URL = process.env.REACT_APP_API_URL;

const Register = () => {
  const { loginUser } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || '/';

  const [form, setForm] = useState({ 
    username: '', 
    email: '', 
    password: '', 
    password2: '' 
  });
  
  const [isLoading, setIsLoading] = useState(false);
  const [showPasswordRules, setShowPasswordRules] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);
  const [passwordValidation, setPasswordValidation] = useState({
    length: false,
    notNumeric: false,
    notSimilar: false,
    matches: false
  });

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handlePasswordFocus = () => {
    setShowPasswordRules(true);
    setPasswordFocused(true);
  };

  const handlePasswordBlur = () => {
    setPasswordFocused(false);
    if (form.password === '' && form.password2 === '') {
      setShowPasswordRules(false);
    }
  };

  useEffect(() => {
    if (passwordFocused) {
      setPasswordValidation({
        length: form.password.length >= 8,
        notNumeric: !/^\d+$/.test(form.password),
        notSimilar: !form.password.toLowerCase().includes(form.username.toLowerCase()) && 
                    !form.password.toLowerCase().includes(form.email.split('@')[0].toLowerCase()),
        matches: form.password === form.password2 && form.password2 !== ''
      });
    }
    // eslint-disable-next-line
  }, [form.password, form.password2, passwordFocused]);

  const validatePassword = () => {
    const errors = [];
    if (form.password.length < 8) errors.push('Your password must contain at least 8 characters.');
    if (/^\d+$/.test(form.password)) errors.push('Your password can\'t be entirely numeric.');
    if (form.password.toLowerCase().includes(form.username.toLowerCase()) || 
        form.password.toLowerCase().includes(form.email.split('@')[0].toLowerCase())) {
      errors.push('Your password can\'t be too similar to your other personal information.');
    }
    return errors;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true); 

    const passwordErrors = validatePassword();
    if (passwordErrors.length > 0) {
      setIsLoading(false); 
      setTimeout(() => {
        passwordErrors.forEach(error => toast.error(error, { duration: 5000 }));
      }, 250); 
      return;
    }

    if (form.password !== form.password2) {
      setIsLoading(false);
      setTimeout(() => toast.error("❌ Passwords don't match", { duration: 5000 }), 250);
      return;
    }

    try {
      const res = await axios.post(`${API_URL}/api/register/`, form);
      if (res.status === 201) {
        const loginSuccess = await loginUser(form.email, form.password);
        
        setTimeout(() => {
          toast.success('✅ Registration successful!', { duration: 2000 });
          if (loginSuccess) {
              navigate(from);
          } else {
              navigate('/login', { state: { from } });
          }
        }, 1500);
      }
    } catch (err) {
      let errorMessage = 'Registration failed';
      if (err.response) {
        if (err.response.data.email) errorMessage = err.response.data.email[0];
        else if (err.response.data.username) errorMessage = err.response.data.username[0];
        else if (err.response.data.password) errorMessage = err.response.data.password[0];
      }
      setIsLoading(false); 
      setTimeout(() => toast.error(`❌ ${errorMessage}`, { duration: 5000 }), 250);
    } 
  };

  return (
    <>
      <AnimatePresence>
        {isLoading && <FullScreenSpinner message="Creating your account..." />}
      </AnimatePresence>

      <AppLayout>
        <GlowingPageContainer $maxWidth="1100px">
          {/* 🚀 Matches login optical vertical centering precisely */}
          <AuthWrapper>
            <RegisterCard
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 25 }}
            >
              <IconWrapper
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 300 }}
              >
                <FaUserPlus size={22} />
              </IconWrapper>
              
              <Title>Create Account</Title>
              <Subtitle>Join EazyShop and start shopping today</Subtitle>

              <form onSubmit={handleSubmit}>
                <InputField
                  type="text"
                  name="username"
                  placeholder="Username"
                  value={form.username}
                  onChange={handleChange}
                  required
                  disabled={isLoading}
                  whileFocus={{ scale: 1.02 }}
                />
                <InputField
                  type="email"
                  name="email"
                  placeholder="Email Address"
                  value={form.email}
                  onChange={handleChange}
                  required
                  disabled={isLoading}
                  whileFocus={{ scale: 1.02 }}
                />
                <InputField
                  type="password"
                  name="password"
                  placeholder="Password"
                  value={form.password}
                  onChange={handleChange}
                  onFocus={handlePasswordFocus}
                  onBlur={handlePasswordBlur}
                  required
                  disabled={isLoading}
                  whileFocus={{ scale: 1.02 }}
                />
                
                <AnimatePresence>
                  {showPasswordRules && (
                    <PasswordRules
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                    >
                      <PasswordRule $valid={passwordValidation.length}>
                        {passwordValidation.length ? <FaCheckCircle /> : <FaCircle className="dot" />} At least 8 characters
                      </PasswordRule>
                      <PasswordRule $valid={passwordValidation.notNumeric}>
                        {passwordValidation.notNumeric ? <FaCheckCircle /> : <FaCircle className="dot" />} Not entirely numeric
                      </PasswordRule>
                      <PasswordRule $valid={passwordValidation.notSimilar}>
                        {passwordValidation.notSimilar ? <FaCheckCircle /> : <FaCircle className="dot" />} Not similar to email/username
                      </PasswordRule>
                    </PasswordRules>
                  )}
                </AnimatePresence>
                
                <InputField
                  type="password"
                  name="password2"
                  placeholder="Confirm Password"
                  value={form.password2}
                  onChange={handleChange}
                  onFocus={handlePasswordFocus}
                  onBlur={handlePasswordBlur}
                  required
                  disabled={isLoading}
                  whileFocus={{ scale: 1.02 }}
                />
                
                <AnimatePresence>
                  {showPasswordRules && (
                    <PasswordRule $valid={passwordValidation.matches} style={{ marginBottom: '0.75rem', marginTop: '-0.25rem' }}>
                      {passwordValidation.matches ? <FaCheckCircle /> : <FaCircle className="dot" />} Passwords match
                    </PasswordRule>
                  )}
                </AnimatePresence>

                <SubmitButton
                  type="submit"
                  disabled={isLoading}
                  whileHover={{ scale: isLoading ? 1 : 1.02 }}
                  whileTap={{ scale: isLoading ? 1 : 0.98 }}
                >
                  {isLoading ? 'Registering...' : 'Create Account'}
                </SubmitButton>
              </form>
              
              <LoginLink>
                Already have an account? <Link to="/login" state={{ from }}>Login now</Link>
              </LoginLink>
            </RegisterCard>
          </AuthWrapper>
        </GlowingPageContainer>
      </AppLayout>
    </>
  );
};

export default Register;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const AuthWrapper = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 64vh; /* Matches the login page positioning perfectly */
  box-sizing: border-box;
`;

const RegisterCard = styled(motion.div)`
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
  padding: 1.25rem 1.75rem; 

  h1 {
    margin: 0.3rem 0 0.15rem 0;
    font-size: 1.4rem;
  }

  p {
    margin: 0 0 0.75rem 0;
    font-size: 0.85rem;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem; 
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
  width: 40px;
  height: 40px;
  margin: 0 auto 0.4rem auto; 
  
  svg {
    width: 18px;
    height: 18px;
  }
`;

const Title = styled.h1`
  color: #0F172A;
  margin: 0 0 0.2rem 0;
  font-size: 1.6rem;
  font-weight: 900;
  letter-spacing: -0.5px;
`;

const Subtitle = styled.p`
  color: #64748B;
  font-size: 0.9rem;
  margin-bottom: 1rem;
`;

const InputField = styled(motion.input)`
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid #E2E8F0;
  background: #F8FAFC;
  border-radius: 12px;
  font-size: 0.9rem;
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

const PasswordRules = styled(motion.div)`
  text-align: left;
  margin: -0.25rem 0 0.5rem 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
`;

const PasswordRule = styled.div`
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: ${props => props.$valid ? '#059669' : '#94A3B8'};
  transition: color 0.3s ease;
  
  svg { font-size: 0.9rem; }
  .dot { font-size: 0.4rem; margin-left: 0.2rem; margin-right: 0.2rem; color: #CBD5E1; }
`;

const SubmitButton = styled(motion.button)`
  width: 100%;
  padding: 0.85rem;
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
  margin-top: 0.25rem;
  box-shadow: 0 4px 15px rgba(11, 132, 87, 0.25);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;

  &:hover:not(:disabled) { box-shadow: 0 6px 20px rgba(11, 132, 87, 0.4); }
  &:disabled { opacity: 0.7; cursor: not-allowed; }
`;

const LoginLink = styled.div`
  margin-top: 1rem;
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