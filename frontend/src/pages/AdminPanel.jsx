// src/pages/AdminPanel.jsx
import { useContext, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import AuthContext from '../context/AuthContext';
import { FaShieldAlt, FaListUl, FaBoxOpen, FaUsers, FaTags, FaCommentAlt } from 'react-icons/fa';
import React from 'react';
import {PageHeader,GlowingPageContainer} from '../styles/SharedPageStyles';
import AppLayout from '../components/AppLayout';

// Import modular sections
import ProductsSection from '../sections/ProductsSection';
import CategoriesSection from '../sections/CategoriesSection';
import UsersSection from '../sections/UsersSection';
import OrdersSection from '../sections/OrdersSection';
import ReviewsSection from '../sections/ReviewsSection';
import AdminLogsSection from '../sections/AdminLogsSection';

const AdminPanel = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [users, setUsers] = useState([]);
  const [products, setProducts] = useState([]);// eslint-disable-next-line
  const [categories, setCategories] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [orders, setOrders] = useState([]);
  const [activeSection, setActiveSection] = useState('logs'); 

  const fetchData = async () => {
      try {
        const [usersRes, productsRes, categoriesRes, reviewsRes, ordersRes] = await Promise.all([
          axiosInstance.get('/api/users/'),
          axiosInstance.get('/api/products/'),
          axiosInstance.get('/api/categories/'),
          axiosInstance.get('/api/reviews/'),
          axiosInstance.get('/api/orders/admin-all/')
        ]);
  
        const usersList = usersRes.data.results || usersRes.data;
        const ordersList = ordersRes.data.results || ordersRes.data;
  
        setUsers(usersList);
        setProducts(productsRes.data.results || productsRes.data);
        setCategories(categoriesRes.data.results || categoriesRes.data);
        setReviews(reviewsRes.data.results || reviewsRes.data);
        
        setOrders(ordersList.map(order => ({
          ...order,
          username: usersList.find(u => u.id === order.user)?.username || 'Unknown'
        })));
      } catch (err) {
        console.error('Failed to load admin data', err);
      }
    };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line
  }, []);

  return (
    <AppLayout>
      <GlowingPageContainer $maxWidth="1100px">
      <AmbientBackground />
      <AdminContainer>
        <PageHeader 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <BadgeTag><FaShieldAlt /> System Administration</BadgeTag>
          <h1>Admin Control Center</h1>
          <p>Monitor platform security, oversee marketplace inventory, and manage operations.</p>
        </PageHeader>

        <NavTabs>
          <TabButton onClick={() => setActiveSection('logs')} $active={activeSection === 'logs'} whileTap={{ scale: 0.97 }}><FaListUl /> Activity Logs</TabButton>
          <TabButton onClick={() => setActiveSection('products')} $active={activeSection === 'products'} whileTap={{ scale: 0.97 }}><FaShieldAlt /> Products</TabButton>
          <TabButton onClick={() => setActiveSection('categories')} $active={activeSection === 'categories'} whileTap={{ scale: 0.97 }}><FaTags /> Categories</TabButton>
          <TabButton onClick={() => setActiveSection('users')} $active={activeSection === 'users'} whileTap={{ scale: 0.97 }}><FaUsers /> Users</TabButton>
          <TabButton onClick={() => setActiveSection('orders')} $active={activeSection === 'orders'} whileTap={{ scale: 0.97 }}><FaBoxOpen /> Orders</TabButton>
          <TabButton onClick={() => setActiveSection('reviews')} $active={activeSection === 'reviews'} whileTap={{ scale: 0.97 }}><FaCommentAlt /> Reviews</TabButton>
        </NavTabs>

        <AnimatePresence mode="wait">
          {activeSection === 'logs' && (
            <SectionWrapper key="logs" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <AdminLogsSection />
            </SectionWrapper>
          )}
          {activeSection === 'products' && (
            <SectionWrapper key="products" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <ProductsSection />
            </SectionWrapper>
          )}
          {activeSection === 'categories' && (
            <SectionWrapper key="categories" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <CategoriesSection />
            </SectionWrapper>
          )}
          {activeSection === 'users' && (
            <SectionWrapper key="users" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <UsersSection users={users} refetch={fetchData} />
            </SectionWrapper>
          )}
          {activeSection === 'orders' && (
            <SectionWrapper key="orders" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <OrdersSection orders={orders} refetch={fetchData} />
            </SectionWrapper>
          )}
          {activeSection === 'reviews' && (
            <SectionWrapper key="reviews" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
              <ReviewsSection reviews={reviews} users={users} products={products} refetch={fetchData} />
            </SectionWrapper>
          )}
        </AnimatePresence>
        </AdminContainer>
      </GlowingPageContainer>
    </AppLayout>
  );
};

export default AdminPanel;

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

const AdminContainer = styled.div`
  position: relative;
  z-index: 1;
  padding: 0 1.5rem;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  box-sizing: border-box;

  @media (min-width: 768px) {
    padding: 0 2rem;
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

const NavTabs = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  justify-content: center;
  margin-bottom: 2.5rem;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  padding: 0.6rem;
  border-radius: 50px;
  border: 1px solid rgba(11, 132, 87, 0.12);
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
  width: fit-content;
  margin-inline: auto;

  @media (min-width: 768px) { gap: 0.8rem; }
`;

const TabButton = styled(motion.button)`
  padding: 10px 20px;
  border-radius: 50px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  border: none;
  transition: all 0.2s ease;
  display: flex; 
  align-items: center; 
  gap: 8px;
  background: ${({ $active }) => ($active ? 'linear-gradient(135deg, #0B8457 0%, #075E3E 100%)' : 'transparent')} !important;
  color: ${({ $active }) => ($active ? '#ffffff' : '#64748B')} !important;
  box-shadow: ${({ $active }) => ($active ? '0 4px 14px rgba(11, 132, 87, 0.25)' : 'none')} !important;

  &:hover {
    color: ${({ $active }) => ($active ? '#ffffff' : '#0F172A')} !important;
  }
`;

const SectionWrapper = styled(motion.div)` width: 100%; `;