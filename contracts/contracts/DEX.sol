// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20T {
    function transferFrom(address,address,uint256) external returns (bool);
    function transfer(address,uint256) external returns (bool);
    function balanceOf(address) external view returns (uint256);
}

contract ResolverDEX {
    uint256 constant FEE_NUM = 997;
    uint256 constant FEE_DEN = 1000;

    struct Pair {
        address tokenA; address tokenB;
        uint256 reserveA; uint256 reserveB;
        bool exists;
    }

    mapping(bytes32=>Pair) public pairs;
    bytes32[] public pairIds;

    event PairCreated(bytes32 pairId, address tokenA, address tokenB);
    event Swapped(bytes32 pairId, address indexed sender, address tokenIn, address tokenOut, uint256 amtIn, uint256 amtOut);
    event LiquidityAdded(bytes32 pairId, uint256 amtA, uint256 amtB);

    function pairId(address a, address b) public pure returns (bytes32) {
        (address t0,address t1) = a<b?(a,b):(b,a);
        return keccak256(abi.encodePacked(t0,t1));
    }

    function createPair(address a, address b) external returns (bytes32 id) {
        require(a!=b,"same token");
        id = pairId(a,b);
        require(!pairs[id].exists,"exists");
        (address t0,address t1)=a<b?(a,b):(b,a);
        pairs[id]=Pair(t0,t1,0,0,true);
        pairIds.push(id);
        emit PairCreated(id,t0,t1);
    }

    function addLiquidity(address a, address b, uint256 amtA, uint256 amtB) external {
        bytes32 id = pairId(a,b);
        Pair storage p = pairs[id];
        require(p.exists,"no pair");
        bool ab = a==p.tokenA;
        (uint256 aa,uint256 ab2) = ab?(amtA,amtB):(amtB,amtA);
        IERC20T(p.tokenA).transferFrom(msg.sender,address(this),aa);
        IERC20T(p.tokenB).transferFrom(msg.sender,address(this),ab2);
        p.reserveA+=aa; p.reserveB+=ab2;
        emit LiquidityAdded(id,aa,ab2);
    }

    function swap(address tokenIn, address tokenOut, uint256 amtIn, uint256 minOut) external returns (uint256 amtOut) {
        bytes32 id = pairId(tokenIn,tokenOut);
        Pair storage p = pairs[id];
        require(p.exists,"no pair");
        bool ab = tokenIn==p.tokenA;
        uint256 rIn  = ab?p.reserveA:p.reserveB;
        uint256 rOut = ab?p.reserveB:p.reserveA;
        require(rIn>0&&rOut>0,"no liquidity");
        uint256 inFee = amtIn*FEE_NUM;
        amtOut = inFee*rOut/(rIn*FEE_DEN+inFee);
        require(amtOut>=minOut,"slippage");
        require(amtOut<rOut,"insufficient liquidity");
        IERC20T(tokenIn).transferFrom(msg.sender,address(this),amtIn);
        IERC20T(tokenOut).transfer(msg.sender,amtOut);
        if(ab){ p.reserveA+=amtIn; p.reserveB-=amtOut; }
        else  { p.reserveB+=amtIn; p.reserveA-=amtOut; }
        emit Swapped(id,msg.sender,tokenIn,tokenOut,amtIn,amtOut);
    }

    function getReserves(address a, address b) external view returns (uint256,uint256) {
        bytes32 id=pairId(a,b); Pair storage p=pairs[id];
        require(p.exists,"no pair");
        bool ab=a==p.tokenA;
        return ab?(p.reserveA,p.reserveB):(p.reserveB,p.reserveA);
    }

    function getAmountOut(address tokenIn, address tokenOut, uint256 amtIn) external view returns (uint256) {
        bytes32 id=pairId(tokenIn,tokenOut); Pair storage p=pairs[id];
        require(p.exists,"no pair");
        bool ab=tokenIn==p.tokenA;
        uint256 rIn=ab?p.reserveA:p.reserveB; uint256 rOut=ab?p.reserveB:p.reserveA;
        uint256 inFee=amtIn*FEE_NUM;
        return inFee*rOut/(rIn*FEE_DEN+inFee);
    }

    function allPairsLength() external view returns (uint256) { return pairIds.length; }
}
