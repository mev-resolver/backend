const hre = require("hardhat");

async function main() {
  const [deployer, bot1, bot2, victim] = await hre.ethers.getSigners();
  
  const resAddr = "0x5FbDB2315678afecb367f032d93F642f64180aa3"; // your RES address
  const olvAddr = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"; // your OLV address
  
  const RES = await hre.ethers.getContractAt("TestToken", resAddr);
  const OLV = await hre.ethers.getContractAt("TestToken", olvAddr);
  
  const amount = hre.ethers.parseEther("10000");
  
  await RES.mint(bot1.address, amount);
  await RES.mint(victim.address, amount);
  await OLV.mint(bot2.address, amount);
  
  console.log(`Minted to bot1 (${bot1.address})`);
  console.log(`Minted to victim (${victim.address})`);
  console.log(`Minted to bot2 (${bot2.address})`);
}

main().catch(console.error);