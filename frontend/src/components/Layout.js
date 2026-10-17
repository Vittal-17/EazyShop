// src/components/Layout.js
import Navbar from './Navbar';
import { Outlet } from 'react-router-dom';
import styled from 'styled-components';

const Layout = () => {
  return (
    <>
      <Navbar />
      <MainWrapper>
        <Outlet />
      </MainWrapper>
    </>
  );
};

const MainWrapper = styled.main`
  padding-top: 76px; /* Matches your exact fixed navbar height */
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  
  /* Forces the child component (Home, Products, etc.) to fill remaining space */
  & > * {
    flex: 1; 
  }
  
  animation: fadeIn 0.5s ease;
  @keyframes fadeIn {
    0% { opacity: 0; transform: translateY(10px); }
    100% { opacity: 1; transform: translateY(0); }
  }
`;

export default Layout;