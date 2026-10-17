// src/pages/ForgotPassword.jsx
import { useState } from 'react';
import axiosInstance from '../utils/axios';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from "react-hot-toast";
import styled from 'styled-components';
import { FaKey, FaEnvelope, FaShieldAlt, FaArrowLeft, FaCheck } from 'react-icons/fa';
import FullScreenSpinner from '../components/FullScreenSpinner';
import AppLayout from '../components/AppLayout';
import { GlowingPageContainer } from '../styles/SharedPageStyles';

const ForgotPassword = () => {
  const [step, setStep] = useState(1); // 1: Email, 2: OTP, 3: New Password
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('Processing...');
  const navigate = useNavigate();

  // Step 1: Request OTP
  const handleRequestOtp = async (e) => {
    e.preventDefault();
    if (!email) {
      toast.error("❌ Please enter your email address");
      return;
    }
    setIsLoading(true);
    setLoadingText('Dispatching secure recovery code...');

    try {
      await axiosInstance.post('/api/password-reset/request/', { email });
      setIsLoading(false);
      toast.success('📬 Recovery OTP sent to your email!');
      setStep(2);
    } catch (err) {
      setIsLoading(false);
      toast.error(err.response?.data?.error || '❌ Failed to send OTP. Try again.');
    }
  };

  // Step 2: Verify OTP
  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    if (!otp || otp.length !== 6) {
      toast.error("❌ Please enter a valid 6-digit OTP code");
      return;
    }
    setIsLoading(true);
    setLoadingText('Verifying authorization code...');

    try {
      await axiosInstance.post('/api/password-reset/verify/', { email, otp });
      setIsLoading(false);
      toast.success('✨ OTP verified successfully!');
      setStep(3);
    } catch (err) {
      setIsLoading(false);
      toast.error(err.response?.data?.error || '❌ Invalid or expired OTP.');
    }
  };

  // Step 3: Set New Password with Real-Time Rule Validations
  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (!newPassword || newPassword.length < 8) {
      toast.error("❌ Password must be at least 8 characters long");
      return;
    }
    if (/^\d+$/.test(newPassword)) {
      toast.error("❌ Password cannot be entirely numeric");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("❌ Passwords do not match");
      return;
    }

    setIsLoading(true);
    setLoadingText('Securing your new password...');

    try {
      await axiosInstance.post('/api/password-reset/confirm/', { 
        email, 
        otp, 
        new_password: newPassword 
      });
      setIsLoading(false);
      toast.success('🔒 Password changed successfully! Please log in.');
      setTimeout(() => navigate('/login'), 1500);
    } catch (err) {
      setIsLoading(false);
      toast.error(err.response?.data?.error || '❌ Failed to reset password.');
    }
  };

  return (
    <>
      <AnimatePresence>
        {isLoading && <FullScreenSpinner message={loadingText} />}
      </AnimatePresence>

      <AppLayout>
        <GlowingPageContainer $maxWidth="1100px">
          <AuthWrapper>
            <ResetCard
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 25 }}
            >
              <IconWrapper
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                key={step}
                transition={{ type: "spring", stiffness: 300 }}
              >
                {step === 1 && <FaEnvelope size={24} />}
                {step === 2 && <FaShieldAlt size={24} />}
                {step === 3 && <FaKey size={24} />}
              </IconWrapper>
              
              <Title>
                {step === 1 && "Forgot Password?"}
                {step === 2 && "Enter Security OTP"}
                {step === 3 && "Create New Password"}
              </Title>
              <Subtitle>
                {step === 1 && "No worries! Enter your registered email address to receive a secure recovery code."}
                {step === 2 && <>We've sent a 6-digit code to <EmailHighlight>{email}</EmailHighlight></>}
                {step === 3 && "Choose and confirm a robust new password to secure your EazyShop account."}
              </Subtitle>
              
              <AnimatePresence mode="wait">
                {/* STEP 1: EMAIL INPUT */}
                {step === 1 && (
                  <FormSection
                    key="step1"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    onSubmit={handleRequestOtp}
                  >
                    <InputField
                      type="email"
                      placeholder="name@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      disabled={isLoading}
                      whileFocus={{ scale: 1.02 }}
                    />
                    <SubmitButton
                      type="submit"
                      disabled={isLoading}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      Send Recovery OTP
                    </SubmitButton>
                  </FormSection>
                )}

                {/* STEP 2: OTP INPUT */}
                {step === 2 && (
                  <FormSection
                    key="step2"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    onSubmit={handleVerifyOtp}
                  >
                    <InputField
                      type="text"
                      maxLength="6"
                      placeholder="123456"
                      value={otp}
                      onChange={(e) => setOtp(e.target.value)}
                      required
                      disabled={isLoading}
                      style={{ textAlign: 'center', letterSpacing: '8px', fontSize: '1.4rem', fontWeight: 'bold' }}
                      whileFocus={{ scale: 1.02 }}
                    />
                    <SubmitButton
                      type="submit"
                      disabled={isLoading}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      Verify OTP Code
                    </SubmitButton>
                  </FormSection>
                )}

                {/* STEP 3: NEW PASSWORD & CONFIRMATION WITH REAL-TIME VALIDATION */}
                {step === 3 && (
                  <FormSection
                    key="step3"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    onSubmit={handleResetPassword}
                  >
                    <InputField
                      type="password"
                      placeholder="Enter new password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      disabled={isLoading}
                      whileFocus={{ scale: 1.02 }}
                    />
                    
                    <InputField
                      type="password"
                      placeholder="Confirm new password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      disabled={isLoading}
                      whileFocus={{ scale: 1.02 }}
                    />

                    {/* Real-time Validation Checklist */}
                    <ValidationList>
                      <ValidationItem $met={newPassword.length >= 8}>
                        {newPassword.length >= 8 ? <FaCheck /> : <BulletDot />}
                        At least 8 characters
                      </ValidationItem>
                      <ValidationItem $met={newPassword.length > 0 && !/^\d+$/.test(newPassword)}>
                        {newPassword.length > 0 && !/^\d+$/.test(newPassword) ? <FaCheck /> : <BulletDot />}
                        Not entirely numeric
                      </ValidationItem>
                      <ValidationItem $met={confirmPassword.length > 0 && newPassword === confirmPassword}>
                        {confirmPassword.length > 0 && newPassword === confirmPassword ? <FaCheck /> : <BulletDot />}
                        Passwords match
                      </ValidationItem>
                    </ValidationList>

                    <SubmitButton
                      type="submit"
                      disabled={isLoading}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      Reset Password
                    </SubmitButton>
                  </FormSection>
                )}
              </AnimatePresence>

              <BackToLogin>
                <Link to="/login"><FaArrowLeft size={12} /> Back to Login</Link>
              </BackToLogin>
            </ResetCard>
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
  height: 100%;
  margin-top: -1.5rem; 

  @media (max-width: 768px) {
    margin-top: 0;
  }
`;

const ResetCard = styled(motion.div)`
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(11, 132, 87, 0.12);
  border-radius: 24px;
  box-shadow: 0 15px 40px -10px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 440px;
  text-align: center;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 1.5rem 2.5rem 2rem 2.5rem; 

  @media (max-width: 768px) {
    padding: 1.5rem 1rem;
    margin: 1rem auto;
    width: 95%;
    background: rgba(255, 255, 255, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-radius: 20px;
  }
`;

const IconWrapper = styled(motion.div)`
  background: #ECFDF5;
  color: #0B8457;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 0 6px rgba(16, 185, 129, 0.1);
  width: 48px;
  height: 48px;
  margin: 0 auto 0.75rem auto; 
  
  svg {
    width: 24px;
    height: 24px;
  }
`;

const Title = styled.h1`
  color: #0F172A;
  margin: 0 0 0.5rem 0;
  font-size: 1.8rem;
  font-weight: 900;
  letter-spacing: -0.5px;
`;

const Subtitle = styled.p`
  color: #64748B;
  font-size: 0.95rem;
  margin-bottom: 2rem;
  line-height: 1.4;
`;

const EmailHighlight = styled.span`
  color: #0B8457;
  font-weight: 700;
`;

const FormSection = styled(motion.form)`
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

const InputField = styled(motion.input)`
  width: 100%;
  padding: 1.1rem 1.2rem;
  border: 1px solid #E2E8F0;
  background: #F8FAFC;
  border-radius: 14px;
  font-size: 1rem;
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

const ValidationList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  text-align: left;
  padding-left: 0.2rem;
  margin-top: -0.2rem;
`;

const ValidationItem = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  font-weight: ${props => props.$met ? '600' : '400'};
  color: ${props => props.$met ? '#10B981' : '#94A3B8'};
  transition: all 0.2s ease;

  svg {
    font-size: 0.75rem;
  }
`;

const BulletDot = styled.span`
  width: 6px;
  height: 6px;
  background-color: #94A3B8;
  border-radius: 50%;
  display: inline-block;
  margin: 0 1px;
`;

const SubmitButton = styled(motion.button)`
  width: 100%;
  padding: 1.1rem;
  background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
  color: white;
  border: none;
  border-radius: 14px;
  font-size: 1.05rem;
  font-weight: 800;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  margin-top: 0.5rem;
  box-shadow: 0 6px 20px rgba(11, 132, 87, 0.25);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: -150%;
    width: 50%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.25), transparent);
    transform: skewX(-25deg);
    animation: shimmer 4s infinite;
  }
  
  @keyframes shimmer { 0% { left: -150%; } 20% { left: 200%; } 100% { left: 200%; } }

  &:hover:not(:disabled) { box-shadow: 0 8px 25px rgba(11, 132, 87, 0.4); }
  &:disabled { opacity: 0.7; cursor: not-allowed; &::after { display: none; } }
`;

const BackToLogin = styled.div`
  margin-top: 2rem;
  
  a {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #64748B;
    text-decoration: none;
    font-size: 0.95rem;
    font-weight: 600;
    transition: color 0.2s ease;

    &:hover { 
      color: #0B8457; 
    }
  }
`;

export default ForgotPassword;