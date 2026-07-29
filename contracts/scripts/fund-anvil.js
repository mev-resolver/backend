const hre = require("hardhat");

async function main() {
  // Anvil's default accounts:
  // #0 deployer: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
  // #1 bot1:    0x70997970C51812dc3A010C7d01b50e0d17dc79C8
  // #2 bot2:    0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
  // #3 victim:  0x90F79bf6EB2c4f870365E785982E1f101E93b906
  const [deployer, bot1, bot2, victim] = await hre.ethers.getSigners();

  const RES_ADDR = "0x5FbDB2315678afecb367f032d93F642f64180aa3"; // replace with your RES address
  const OLV_ADDR = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"; // replace with your OLV address

  const RES = await hre.ethers.getContractAt("TestToken", RES_ADDR);
  const OLV = await hre.ethers.getContractAt("TestToken", OLV_ADDR);

  const amount = hre.ethers.parseEther("10000"); // 10,000 tokens

  console.log("Minting RES to bot1 and victim...");
  await RES.mint(bot1.address, amount);
  await RES.mint(victim.address, amount);

  console.log("Minting OLV to bot2...");
  await OLV.mint(bot2.address, amount);

  console.log("✅ Done.");
  console.log(`Bot1 (${bot1.address}) RES balance: ${hre.ethers.formatEther(await RES.balanceOf(bot1.address))}`);
  console.log(`Bot2 (${bot2.address}) OLV balance: ${hre.ethers.formatEther(await OLV.balanceOf(bot2.address))}`);
  console.log(`Victim (${victim.address}) RES balance: ${hre.ethers.formatEther(await RES.balanceOf(victim.address))}`);
}

main().catch(console.error);