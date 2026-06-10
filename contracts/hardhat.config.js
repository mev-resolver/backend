require('@nomicfoundation/hardhat-toolbox');
require('dotenv').config({ path: '.env' });

const pk = process.env.PRIVATE_KEY_RELAYER;

module.exports = {
  solidity: { version: '0.8.20', settings: { optimizer: { enabled: true, runs: 200 } } },
  networks: {
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL || '',
      accounts: pk ? [pk] : [],
    },
  },
};
