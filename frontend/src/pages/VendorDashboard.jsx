// src/pages/VendorDashboard.jsx
import { useState, useContext, useEffect } from 'react';
import styled from 'styled-components';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { FaChartLine, FaBox, FaStar, FaStore } from 'react-icons/fa';
import AuthContext from '../context/AuthContext';
import {PageHeader,GlowingPageContainer} from '../styles/SharedPageStyles';
import AppLayout from '../components/AppLayout';

// Import Modular Sections
import VendorSalesSection from '../sections/vendor/VendorSalesSection';
import VendorProductsSection from '../sections/vendor/VendorProductsSection';
import VendorReviewsSection from '../sections/vendor/VendorReviewsSection';

const VendorDashboard = () => {
  const { user } = useContext(AuthContext);
  const navigate = useNavigate(); // 🚀 Changed from useNavigateInstance to navigate
  const [activeTab, setActiveTab] = useState('sales');

  useEffect(() => {
    if (user && user.role !== 'seller' && user.role !== 'admin') {
      navigate('/dashboard'); 
    }
  }, [user, navigate]);

  if (!user || (user.role !== 'seller' && user.role !== 'admin')) return null;

  return (
    <AppLayout>
      <GlowingPageContainer $maxWidth="1100px">
      <AmbientBackground />
      <DashboardContainer>
        <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <PageHeader>
            <BadgeTag><FaStore /> Vendor Portal</BadgeTag>
            <h1>Marketplace Management</h1>
            <p>Welcome back, <strong>{user.username}</strong>. Oversee your catalog performance and customer feedback.</p>
          </PageHeader>

          <TabBar>
            <Tab $active={activeTab === 'sales'} onClick={() => setActiveTab('sales')} whileTap={{ scale: 0.97 }}>
              <FaChartLine /> Sales & Fulfillment
            </Tab>
            <Tab $active={activeTab === 'products'} onClick={() => setActiveTab('products')} whileTap={{ scale: 0.97 }}>
              <FaBox /> My Product Catalog
            </Tab>
            <Tab $active={activeTab === 'reviews'} onClick={() => setActiveTab('reviews')} whileTap={{ scale: 0.97 }}>
              <FaStar /> Customer Reviews
            </Tab>
          </TabBar>

          <ContentArea>
            {activeTab === 'sales' && <VendorSalesSection />}
            {activeTab === 'products' && <VendorProductsSection />}
            {activeTab === 'reviews' && <VendorReviewsSection />}
          </ContentArea>
        </motion.div>
      </DashboardContainer>
      </GlowingPageContainer>
      </AppLayout>
  );
};

export default VendorDashboard;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const AmbientBackground = styled.div`
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 1400px;
  height: 600px;
  background: radial-gradient(circle at 50% 10%, rgba(11, 132, 87, 0.08) 0%, transparent 60%);
  pointer-events: none;
  z-index: 0;
`;

const DashboardContainer = styled.div`
  position: relative;
  z-index: 1;
  max-width: 1100px; 
  margin: 0 auto; 
  padding: 0 1.5rem; 
  box-sizing: border-box;

  @media (max-width: 768px) { 
    padding: 0 1rem; 
  }
`;

const BadgeTag = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: rgba(11, 132, 87, 0.1);
  color: #0B8457;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.4rem 1rem;
  border-radius: 50px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 1rem;
  border: 1px solid rgba(11, 132, 87, 0.2);
`;

const TabBar = styled.div` 
  display: flex; 
  gap: 0.8rem; 
  margin-bottom: 2.5rem; 
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  padding: 0.5rem;
  border-radius: 50px;
  border: 1px solid rgba(11, 132, 87, 0.12);
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
  width: fit-content;
  margin-inline: auto;

  /* 🚀 MOBILE FIX: Allow tabs to wrap gracefully instead of bleeding off screen */
  @media (max-width: 768px) {
    width: 100%;
    flex-wrap: wrap;
    justify-content: center;
    border-radius: 24px;
    padding: 0.5rem;
  }
`;

const Tab = styled(motion.button)` 
  display: flex; 
  align-items: center; 
  gap: 0.6rem; 
  background: ${props => props.$active ? 'linear-gradient(135deg, #0B8457 0%, #075E3E 100%)' : 'transparent'}; 
  color: ${props => props.$active ? '#ffffff' : '#64748B'}; 
  border: none; 
  padding: 0.7rem 1.6rem; 
  border-radius: 50px; 
  font-weight: 700; 
  font-size: 0.95rem; 
  cursor: pointer; 
  transition: color 0.2s; 
  white-space: nowrap; 
  box-shadow: ${props => props.$active ? '0 4px 14px rgba(11, 132, 87, 0.25)' : 'none'};

  &:hover { 
    color: ${props => props.$active ? '#ffffff' : '#0F172A'}; 
  }

  /* 🚀 MOBILE FIX: Dynamically resize tabs to fill the available space */
  @media (max-width: 768px) {
    padding: 0.6rem 1rem;
    font-size: 0.85rem;
    flex: 1 1 auto; 
    justify-content: center;
  }
`;

const ContentArea = styled.div` 
  min-height: 400px; 
`;