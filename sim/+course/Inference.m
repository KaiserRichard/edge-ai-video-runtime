classdef Inference < matlab.System
    methods
        function o=Inference(varargin), setProperties(o,nargin,varargin{:}); end
    end
    % IID resampling from measured service seconds; no Statistics Toolbox.
    properties (Nontunable), Samples=.0125; Seed=3; end
    properties (Access=private), Stream; end
    methods (Access=protected)
        function setupImpl(o)
            assert(~isempty(o.Samples) && all(isfinite(o.Samples(:))) && all(o.Samples(:)>0));
            o.Stream=RandStream('mt19937ar','Seed',o.Seed);
        end
        function [finish,service]=stepImpl(o,start)
            k=1+floor(rand(o.Stream)*numel(o.Samples)); service=o.Samples(k);
            finish=start+service;
        end
        function resetImpl(o), setupImpl(o); end
    end
end
