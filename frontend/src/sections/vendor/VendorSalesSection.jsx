// src/sections/vendor/VendorSalesSection.jsx
import { useState, useContext, useEffect } from 'react';
import styled from 'styled-components';
import { motion } from 'framer-motion';// eslint-disable-next-line
import { FaTruck, FaBoxOpen, FaMoneyBillWave, FaShieldAlt, FaMapMarkerAlt, FaUser } from 'react-icons/fa';
import { toast } from 'react-hot-toast';
import AuthContext from '../../context/AuthContext';
import { formatINR } from '../../utils/currency';

const VendorSalesSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [sales, setSales] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);

  const fetchSales = async () => {
    setIsLoading(true);
    try {
      // Fetch vendor sales and all orders in parallel to cross-reference addresses and usernames safely
      const [salesRes, ordersRes, usersRes] = await Promise.all([
        axiosInstance.get('/api/vendor-sales/'),
        axiosInstance.get('/api/orders/?page_size=1000').catch(() => ({ data: [] })),
        axiosInstance.get('/api/users/?page_size=1000').catch(() => ({ data: [] }))
      ]);

      const rawSales = salesRes.data.results || salesRes.data;
      const allOrders = ordersRes.data.results || ordersRes.data || [];
      const allUsers = usersRes.data.results || usersRes.data || [];

      // Map shipping address and buyer username from matching orders
      const enrichedSales = rawSales.map(sale => {
        // match by sale.order or sale.order_id
        const matchedOrder = allOrders.find(o => o.id === sale.order || o.id === sale.order_id);
        
        let buyerName = sale.username || sale.customer_name;
        if (!buyerName && matchedOrder) {
          const matchedUser = allUsers.find(u => u.id === matchedOrder.user);
          buyerName = matchedUser?.username || `Customer #${matchedOrder.user}`;
        }

        return {
          ...sale,
          shipping_address: sale.shipping_address || sale.address || matchedOrder?.shipping_address || 'Standard Shipping Destination',
          username: buyerName || 'Verified Buyer'
        };
      });

      setSales(enrichedSales);
    } catch (error) {
      toast.error('❌ Failed to load your sales data.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSales();
    // eslint-disable-next-line
  }, []);

  const handleUpdateStatus = async (itemId, newStatus) => {
    setUpdatingId(itemId);
    try {
      await axiosInstance.patch(`/api/vendor-sales/${itemId}/update_status/`, { status: newStatus });
      toast.success(`📦 Item marked as ${newStatus}!`);
      setSales(prev => prev.map(sale => sale.id === itemId ? { ...sale, status: newStatus } : sale));
    } catch (error) {
      toast.error('❌ Failed to update status.');
    } finally {
      setUpdatingId(null);
    }
  };

  const totalEarnings = sales.reduce((sum, item) => {
    if (item.status !== 'cancelled') {
      return sum + parseFloat(item.seller_earnings || 0);
    }
    return sum;
  }, 0);

  if (isLoading) {
    return <LoadingWrapper><Spinner /><LoadingText>Loading Sales Data...</LoadingText></LoadingWrapper>;
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <StatsCard whileHover={{ y: -2 }} transition={{ duration: 0.2 }}>
        <div className="stat-info">
          <p>Total Net Earnings</p>
          <h2>{formatINR(totalEarnings)}</h2>
        </div>
        <FaMoneyBillWave size={48} color="#ffffff" opacity={0.25} />
      </StatsCard>

      {sales.length === 0 ? (
        <EmptyState>
          <span className="emoji">💰</span>
          <h3>No sales recorded yet</h3>
          <p>You haven't made any sales yet. Keep listing great products!</p>
        </EmptyState>
      ) : (
        <SalesList>
          {sales.map((sale) => (
            <SaleCard key={sale.id} whileHover={{ y: -2 }} transition={{ duration: 0.2 }}>
              <SaleHeader>
                <div>
                  <h3>Order #{sale.order || sale.order_id || 'N/A'}</h3>
                  <span className={`status-badge ${sale.status || 'pending'}`}>
                    {(sale.status || 'pending').toUpperCase()}
                  </span>
                </div>
                <EarningsBadge>+ {formatINR(sale.seller_earnings || 0)}</EarningsBadge>
              </SaleHeader>
              
              <SaleBody>
                <div className="product-info">
                  <div className="img-wrap">
                    <img src={sale.image_url} alt={sale.name} />
                  </div>
                  <div>
                    <h4>{sale.name}</h4>
                    <p>Qty: {sale.quantity} <span>•</span> Price: ₹{sale.price}</p>
                  </div>
                </div>

                <ActionGroup>
                  {sale.status === 'pending' && (
                    <StatusButton 
                      className="ship-btn" 
                      onClick={() => handleUpdateStatus(sale.id, 'shipped')}
                      disabled={updatingId === sale.id}
                      whileTap={{ scale: 0.97 }}
                    >
                      <FaTruck /> {updatingId === sale.id ? 'Updating...' : 'Mark as Shipped'}
                    </StatusButton>
                  )}
                  {sale.status === 'shipped' && (
                    <InfoNotice>
                      <FaShieldAlt color="#3B82F6" /> Shipped — Awaiting Admin Delivery Verification
                    </InfoNotice>
                  )}
                  {sale.status === 'delivered' && (
                    <p style={{ color: '#047857', fontWeight: '700', fontSize: '0.9rem' }}>
                      ✅ Fulfillment Complete (Admin Verified)
                    </p>
                  )}
                  {sale.status === 'cancelled' && (
                    <p style={{ color: '#DC2626', fontWeight: '700', fontSize: '0.9rem' }}>
                      🚫 Order Cancelled
                    </p>
                  )}
                </ActionGroup>
              </SaleBody>

              {/* 🚀 LOGISTICS SHIPPING INFO PANEL */}
              <ShippingDetailsBox>
                <div className="shipping-row">
                  <FaUser className="icon" />
                  <span>Buyer: <strong>{sale.username}</strong></span>
                </div>
                <div className="shipping-row">
                  <FaMapMarkerAlt className="icon" />
                  <span>Destination: <strong>{sale.shipping_address}</strong></span>
                </div>
              </ShippingDetailsBox>
            </SaleCard>
          ))}
        </SalesList>
      )}
    </motion.div>
  );
};

export default VendorSalesSection;

// ==========================================
// STYLED COMPONENTS
// ==========================================

const LoadingWrapper = styled.div` display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 0; `;
const Spinner = styled.div` width: 45px; height: 45px; border: 4px solid #E2E8F0; border-top: 4px solid #0B8457; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; @keyframes spin { to { transform: rotate(360deg); } } `;
const LoadingText = styled.div` font-size: 1.1rem; font-weight: 600; color: #0B8457; `;

const StatsCard = styled(motion.div)` 
  background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); 
  color: white; 
  padding: 2.2rem; 
  border-radius: 24px; 
  display: flex; 
  justify-content: space-between; 
  align-items: center; 
  margin-bottom: 2rem; 
  box-shadow: 0 10px 30px rgba(11, 132, 87, 0.25); 
  border: 1px solid rgba(255, 255, 255, 0.15);
  
  .stat-info {
    p { margin: 0; color: #A7F3D0; font-weight: 800; text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px; } 
    h2 { margin: 0.4rem 0 0 0; font-size: 2.5rem; color: #ffffff; font-weight: 900; letter-spacing: -1px; } 
  }
`;

const EmptyState = styled.div` 
  text-align: center; padding: 5rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1; 
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; } 
`;

const SalesList = styled.div` display: flex; flex-direction: column; gap: 1.5rem; `;

const SaleCard = styled(motion.div)` 
  background: white; border-radius: 20px; padding: 1.8rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); 
`;

const SaleHeader = styled.div` 
  display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #F1F5F9; padding-bottom: 1rem; margin-bottom: 1.2rem; 
  
  h3 { margin: 0 0 0.4rem 0; color: #0F172A; font-size: 1.15rem; font-weight: 800; } 
  
  .status-badge { 
    font-size: 0.75rem; font-weight: 800; padding: 0.3rem 0.8rem; border-radius: 50px; text-transform: uppercase; letter-spacing: 0.5px; 
    &.pending { background: #FEF3C7; color: #B45309; border: 1px solid rgba(245, 158, 11, 0.3); } 
    &.shipped { background: #DBEAFE; color: #1D4ED8; border: 1px solid rgba(59, 130, 246, 0.3); } 
    &.delivered { background: #ECFDF5; color: #047857; border: 1px solid rgba(16, 185, 129, 0.3); } 
    &.cancelled { background: #FEF2F2; color: #DC2626; border: 1px solid rgba(239, 68, 68, 0.3); } 
  } 
`;

const EarningsBadge = styled.div` 
  background: #ECFDF5; color: #047857; font-weight: 900; padding: 0.5rem 1.2rem; border-radius: 12px; font-size: 1.15rem; border: 1px solid rgba(16, 185, 129, 0.3); 
`;

const SaleBody = styled.div` 
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; 
  .product-info { 
    display: flex; align-items: center; gap: 1.2rem; 
    .img-wrap {
      width: 65px; height: 65px; background: #ffffff; border-radius: 12px; padding: 4px; border: 1px solid #E2E8F0; display: flex; align-items: center; justify-content: center;
      img { width: 100%; height: 100%; border-radius: 8px; object-fit: contain; mix-blend-mode: multiply; } 
    }
    h4 { margin: 0 0 0.3rem 0; color: #0F172A; font-weight: 700; font-size: 1.05rem; } 
    p { margin: 0; color: #64748B; font-size: 0.9rem; font-weight: 500; span { margin: 0 0.3rem; color: #CBD5E1; } } 
  } 
`;

const ActionGroup = styled.div` display: flex; align-items: center; `;

const StatusButton = styled(motion.button)` 
  display: flex; align-items: center; gap: 0.5rem; padding: 0.7rem 1.4rem; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; transition: all 0.2s; color: white; font-size: 0.9rem; box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  &:disabled { opacity: 0.6; cursor: not-allowed; box-shadow: none; } 
  &.ship-btn { background: #3B82F6; &:hover:not(:disabled) { background: #2563EB; } } 
`;

const InfoNotice = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #EFF6FF;
  color: #1E40AF;
  padding: 0.6rem 1rem;
  border-radius: 10px;
  font-size: 0.9rem;
  font-weight: 700;
  border: 1px solid rgba(59, 130, 246, 0.2);
`;

const ShippingDetailsBox = styled.div`
  margin-top: 1.2rem;
  padding-top: 1rem;
  border-top: 1px dashed #E2E8F0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  background: #F8FAFC;
  padding: 1rem;
  border-radius: 14px;
  border: 1px solid #F1F5F9;

  .shipping-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.9rem;
    color: #475569;

    .icon {
      color: #0B8457;
      flex-shrink: 0;
    }

    strong {
      color: #0F172A;
    }
  }
`;