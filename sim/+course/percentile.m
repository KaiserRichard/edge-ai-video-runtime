function y=percentile(x,p)
% Linear interpolation of order statistics, no toolbox dependency.
x=sort(x(isfinite(x))); assert(all(p>=0 & p<=100));
if isempty(x), y=NaN(size(p)); return; end
r=1+(numel(x)-1)*p/100; a=floor(r); b=ceil(r);
y=reshape(x(a),size(p)).*(b-r)+reshape(x(b),size(p)).*(r-a);
y(a==b)=x(a(a==b));
end
