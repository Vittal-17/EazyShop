// src/components/ProtectedRoute.js
import { useContext, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import AuthContext from '../context/AuthContext';
import styled, { keyframes } from 'styled-components';

const ProtectedRoute = ({ children, adminOnly = false }) => {
  const { user } = useContext(AuthContext);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const timeout = setTimeout(() => setChecking(false), 1000); // faster check
    return () => clearTimeout(timeout);
  }, []);

  if (checking) {
    return (
      <LoadingWrapper>
        <Spinner />
        <LoadingText>Checking access...</LoadingText>
      </LoadingWrapper>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (adminOnly && user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return children;
};

export default ProtectedRoute;

// Styled components for loading
const spin = keyframes`
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
`;

const LoadingWrapper = styled.div`
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
`;

const Spinner = styled.div`
  width: 50px;
  height: 50px;
  border: 5px solid #e0e0e0;
  border-top: 5px solid #4caf50;
  border-radius: 50%;
  animation: ${spin} 1s linear infinite;
  margin-bottom: 1rem;
`;

const LoadingText = styled.div`
  font-size: 1.2rem;
  color: #4caf50;
  font-weight: 600;
`;
