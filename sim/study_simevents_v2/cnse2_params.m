function cnse2_params(m,c)
% Event actions accept numeric scalars only, so expose the three values they use.
ws=get_param(m,'ModelWorkspace');
assignin(ws,'payload',c.payload);
assignin(ws,'linkBitRate',c.rate);
assignin(ws,'playoutDepth',c.depth);
end
