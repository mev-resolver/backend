require('@nomicfoundation/hardhat-toolbox');
require('dotenv').config({ path: '.env' });

const pk = process.env.PRIVATE_KEY_RELAYER;

module.exports = {
  solidity: { version: '0.8.20', settings: { optimizer: { enabled: true, runs: 200 } } },
  networks: {
    // production
    // sepolia: {
    //   url: process.env.SEPOLIA_RPC_URL || '',
    //   accounts: pk ? [pk] : [],
    // },
    // local
    // For local Anvil node
    anvil: {
      url: "http://127.0.0.1:8545",
      accounts: {
        // The default mnemonic Anvil uses
        mnemonic: "test test test test test test test test test test test junk",
      },
      chainId: 31337,
    }
  },
};
